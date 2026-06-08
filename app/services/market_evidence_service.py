"""
Synchronous market evidence service for TradingAgents analysts.

The FastAPI crawler pipeline writes rolling evidence into MongoDB. TradingAgents
analyst nodes run inside worker threads, so this module intentionally uses
synchronous I/O and pymongo to read or opportunistically refresh that evidence
without touching the main async event loop.
"""
from __future__ import annotations

import hashlib
import html
import json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

import httpx
from pymongo import MongoClient, ReplaceOne
from pymongo.errors import BulkWriteError

from app.core.config import settings
from app.services.investment_daily_service import (
    THEME_KEYWORDS,
    _jsonable,
    _normalize_code,
    _parse_dt,
    _safe_float,
    _safe_int,
    _sentiment_label,
    _sentiment_score,
)

logger = logging.getLogger(__name__)


SOURCE_WEIGHTS = {
    "财联社": 1.18,
    "东方财富": 1.0,
    "东方财富股吧": 0.72,
    "东方财富研报": 1.08,
}


class MarketEvidenceService:
    """Build stock-specific evidence packs from rolling crawlers."""

    def __init__(self) -> None:
        self._indexes_ready = False

    def _client(self) -> MongoClient:
        return MongoClient(
            settings.MONGO_URI,
            serverSelectionTimeoutMS=settings.MONGO_SERVER_SELECTION_TIMEOUT_MS,
            connectTimeoutMS=settings.MONGO_CONNECT_TIMEOUT_MS,
            socketTimeoutMS=settings.MONGO_SOCKET_TIMEOUT_MS,
        )

    def _ensure_indexes(self, db) -> None:
        if self._indexes_ready:
            return
        try:
            db.market_documents.create_index([("doc_key", 1)], unique=True, background=True)
            db.market_documents.create_index([("symbols", 1), ("published_at", -1)], background=True)
            db.market_documents.create_index([("document_type", 1), ("published_at", -1)], background=True)
            db.global_events.create_index([("published_at", -1), ("severity", -1)], background=True)
            db.crawler_runs.create_index([("job_id", 1), ("started_at", -1)], background=True)
            self._indexes_ready = True
        except Exception as e:
            logger.debug("市场证据索引检查失败: %s", e)

    def refresh_stock_evidence_sync(
        self,
        symbol: str,
        *,
        company_name: str = "",
        max_news: int = 24,
        max_comments: int = 20,
    ) -> Dict[str, Any]:
        """Best-effort single-stock refresh before an analysis run."""
        code = _normalize_code(symbol)
        if not code:
            return {"status": "skipped", "reason": "invalid_symbol", "symbol": symbol}

        started_at = datetime.utcnow()
        documents: List[Dict[str, Any]] = []
        errors: List[str] = []

        keywords = [code]
        if company_name and company_name not in keywords:
            keywords.append(company_name)
        keywords.extend([f"{code} 公告", f"{company_name or code} 研报"])

        for keyword in [item for item in keywords if item][:4]:
            try:
                doc_type = "announcement" if "公告" in keyword else "research_report" if "研报" in keyword else "stock_news"
                documents.extend(self._fetch_eastmoney_search(
                    keyword,
                    max(6, max_news // 3),
                    symbol=code,
                    company_name=company_name,
                    document_type=doc_type,
                ))
            except Exception as e:
                errors.append(f"eastmoney:{keyword}:{e}")

        try:
            documents.extend(self._fetch_cls_filtered(code, company_name, limit=max_news))
        except Exception as e:
            errors.append(f"cls:{e}")

        try:
            comments = self._fetch_guba_posts(code, limit=max_comments)
            documents.extend(self._normalize_social_documents(comments))
        except Exception as e:
            errors.append(f"guba:{e}")

        try:
            documents.extend(self._fetch_research_reports(code, limit=6))
        except Exception as e:
            errors.append(f"research:{e}")

        saved = 0
        try:
            with self._client() as client:
                db = client[settings.MONGO_DB]
                self._ensure_indexes(db)
                saved = self._save_documents(db, documents)
                db.crawler_runs.insert_one({
                    "job_id": "stock_evidence_refresh",
                    "started_at": started_at,
                    "ended_at": datetime.utcnow(),
                    "status": "ready" if saved or documents else "partial",
                    "symbol": code,
                    "documents_seen": len(documents),
                    "documents_saved": saved,
                    "errors": errors[:8],
                    "sources": [
                        {
                            "source": "stock_evidence_refresh",
                            "fetched": len(documents),
                            "saved": saved,
                            "failed": len(errors),
                            "latest_publish_time": max([d.get("published_at") for d in documents if d.get("published_at")] or [None]),
                            "message": "单股分析前证据补抓",
                        }
                    ],
                })
        except Exception as e:
            errors.append(f"mongo:{e}")
            logger.warning("单股证据入库失败 %s: %s", code, e)

        return _jsonable({
            "status": "ready" if saved or documents else "partial",
            "symbol": code,
            "documents_seen": len(documents),
            "documents_saved": saved,
            "errors": errors[:8],
            "started_at": started_at,
            "ended_at": datetime.utcnow(),
        })

    def build_stock_evidence_context(
        self,
        symbol: str,
        *,
        company_name: str = "",
        hours: Optional[int] = None,
        refresh_if_stale: bool = True,
        max_chars: int = 9000,
    ) -> str:
        """Return a compact markdown evidence pack for LLM prompts."""
        if not settings.MARKET_INTELLIGENCE_INJECT_TO_ANALYSIS:
            return ""

        code = _normalize_code(symbol)
        if not code:
            return ""

        hours = hours or settings.MARKET_INTELLIGENCE_ANALYSIS_EVIDENCE_HOURS
        cutoff = datetime.utcnow() - timedelta(hours=hours)

        with self._client() as client:
            db = client[settings.MONGO_DB]
            self._ensure_indexes(db)

            latest = db.market_documents.find_one(
                {"symbols": code},
                sort=[("published_at", -1)],
            )
            if refresh_if_stale and self._is_stale(latest):
                self.refresh_stock_evidence_sync(code, company_name=company_name)

            docs = list(db.market_documents.find(
                {"symbols": code, "published_at": {"$gte": cutoff}},
                sort=[("published_at", -1)],
                limit=80,
            ))
            signal = db.stock_signals.find_one({"code": code}, sort=[("signal_date", -1), ("updated_at", -1)])
            theme_names = self._themes_from_documents(docs)
            event_query: Dict[str, Any] = {
                "published_at": {"$gte": cutoff},
                "$or": [{"mapped_stocks": code}],
            }
            if theme_names:
                event_query["$or"].append({"mapped_themes": {"$in": theme_names}})
            events = list(db.global_events.find(event_query, sort=[("severity", -1), ("published_at", -1)], limit=10))
            run = db.crawler_runs.find_one(sort=[("ended_at", -1)])

        return self._format_context(
            code=code,
            company_name=company_name,
            docs=docs,
            events=events,
            signal=signal,
            latest_run=run,
            hours=hours,
            max_chars=max_chars,
        )

    def _is_stale(self, latest: Optional[Dict[str, Any]]) -> bool:
        if not latest:
            return True
        published = _parse_dt(latest.get("published_at"))
        max_age = settings.MARKET_INTELLIGENCE_ANALYSIS_REFRESH_MAX_AGE_MINUTES
        return (datetime.utcnow() - published).total_seconds() > max_age * 60

    def _fetch_eastmoney_search(
        self,
        keyword: str,
        limit: int,
        *,
        symbol: Optional[str],
        company_name: str = "",
        document_type: str,
    ) -> List[Dict[str, Any]]:
        param = {
            "uid": "",
            "keyword": keyword,
            "type": ["cmsArticleWebOld"],
            "client": "web",
            "clientType": "web",
            "clientVersion": "curr",
            "param": {
                "cmsArticleWebOld": {
                    "searchScope": "default",
                    "sort": "default",
                    "pageIndex": 1,
                    "pageSize": limit,
                    "preTag": "",
                    "postTag": "",
                }
            },
        }
        cb = f"jQuery{int(time.time() * 1000)}"
        params = {"cb": cb, "param": json.dumps(param, ensure_ascii=False), "_": str(int(time.time() * 1000))}
        headers = {"User-Agent": "Mozilla/5.0 TradingAgents-CN/1.0", "Referer": "https://so.eastmoney.com/"}
        with httpx.Client(timeout=10, headers=headers, follow_redirects=True, trust_env=False) as client:
            response = client.get("https://search-api-web.eastmoney.com/search/jsonp", params=params)
            response.raise_for_status()
            text = response.text.strip()
        if "(" in text and text.endswith(")"):
            text = text[text.find("(") + 1: -1]
        data = json.loads(text)
        articles = self._extract_articles(data)
        docs = []
        for article in articles[:limit]:
            title = self._clean_html(str(article.get("title") or ""))
            content = self._clean_html(str(article.get("content") or article.get("summary") or ""))
            if not title:
                continue
            url = str(article.get("url") or article.get("Url") or "")
            relevance_text = f"{title} {content} {url}"
            if symbol and symbol not in relevance_text and (not company_name or company_name not in relevance_text):
                continue
            published = _parse_dt(article.get("date") or article.get("time") or article.get("showTime"))
            docs.append(self._document(
                document_type=document_type,
                title=title,
                content=content,
                source=str(article.get("source") or article.get("mediaName") or "东方财富"),
                url=url,
                published_at=published,
                symbols=[symbol] if symbol else [],
                data_source="eastmoney_search",
                metadata={"keyword": keyword},
            ))
        return docs

    def _fetch_cls_filtered(self, symbol: str, company_name: str, *, limit: int) -> List[Dict[str, Any]]:
        headers = {"User-Agent": "Mozilla/5.0 TradingAgents-CN/1.0", "Referer": "https://www.cls.cn/"}
        with httpx.Client(timeout=8, headers=headers, follow_redirects=True, trust_env=False) as client:
            response = client.get(
                "https://www.cls.cn/api/sw",
                params={"app": "CailianpressWeb", "os": "web", "sv": "7.7.5"},
            )
            response.raise_for_status()
            data = response.json()

        docs = []
        for article in self._find_dict_list(data)[:limit * 2]:
            title = str(article.get("title") or article.get("brief") or article.get("content") or "").strip()
            content = str(article.get("content") or article.get("brief") or "")
            if not title:
                continue
            text = f"{title} {content}"
            if symbol not in text and (not company_name or company_name not in text):
                continue
            publish_raw = article.get("ctime") or article.get("time") or article.get("modified_time")
            published = datetime.fromtimestamp(publish_raw) if isinstance(publish_raw, (int, float)) and publish_raw > 10_000 else _parse_dt(publish_raw)
            docs.append(self._document(
                document_type="stock_news",
                title=title[:180],
                content=content,
                source="财联社",
                url=str(article.get("shareurl") or article.get("url") or "https://www.cls.cn/telegraph"),
                published_at=published,
                symbols=[symbol],
                data_source="cls_telegraph",
                metadata={},
            ))
            if len(docs) >= limit:
                break
        return docs

    def _fetch_guba_posts(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        headers = {"User-Agent": "Mozilla/5.0 TradingAgents-CN/1.0", "Referer": "https://guba.eastmoney.com/"}
        with httpx.Client(timeout=8, headers=headers, follow_redirects=True, trust_env=False) as client:
            response = client.get(f"https://guba.eastmoney.com/list,{symbol}.html")
            response.raise_for_status()
            text = response.text

        posts: List[Dict[str, Any]] = []
        marker = "var article_list="
        start = text.find(marker)
        if start >= 0:
            try:
                data, _ = json.JSONDecoder().raw_decode(text[start + len(marker):])
                rows = data.get("re") if isinstance(data, dict) else []
            except Exception:
                rows = []
            for row in rows or []:
                title = str(row.get("post_title") or "").strip()
                if not title:
                    continue
                post_id = str(row.get("post_id") or hashlib.sha1(title.encode("utf-8")).hexdigest()[:16])
                posts.append({
                    "message_id": f"eastmoney_guba:{symbol}:{post_id}",
                    "symbol": symbol,
                    "content": title,
                    "publish_time": _parse_dt(row.get("post_publish_time") or row.get("post_display_time") or row.get("post_last_time")),
                    "url": f"https://guba.eastmoney.com/news,{symbol},{post_id}.html" if post_id else f"https://guba.eastmoney.com/list,{symbol}.html",
                    "author": str(row.get("user_nickname") or "东方财富股吧用户"),
                    "views": _safe_int(row.get("post_click_count")),
                    "comments": _safe_int(row.get("post_comment_count")),
                    "likes": _safe_int(row.get("post_like_count")),
                })
                if len(posts) >= limit:
                    break
        return posts

    def _normalize_social_documents(self, posts: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        docs = []
        for post in posts:
            content = str(post.get("content") or "").strip()
            symbol = _normalize_code(post.get("symbol"))
            if not content or not symbol:
                continue
            docs.append(self._document(
                document_type="social_comment",
                title=content[:90],
                content=content,
                source="东方财富股吧",
                url=str(post.get("url") or ""),
                published_at=_parse_dt(post.get("publish_time")),
                symbols=[symbol],
                data_source="eastmoney_guba",
                metadata={
                    "message_id": post.get("message_id"),
                    "author": post.get("author"),
                    "engagement": {
                        "views": _safe_int(post.get("views")),
                        "likes": _safe_int(post.get("likes")),
                        "comments": _safe_int(post.get("comments")),
                    },
                },
            ))
        return docs

    def _fetch_research_reports(self, symbol: str, *, limit: int = 6) -> List[Dict[str, Any]]:
        try:
            import akshare as ak
        except Exception:
            return []
        try:
            try:
                df = ak.stock_research_report_em(symbol=symbol)
            except TypeError:
                df = ak.stock_research_report_em(symbol)
        except Exception as e:
            logger.debug("AKShare研报获取失败 %s: %s", symbol, e)
            return []
        if df is None or getattr(df, "empty", True):
            return []

        docs = []
        for _, row in df.head(limit).iterrows():
            title = str(row.get("报告名称") or row.get("标题") or row.get("title") or "").strip()
            if not title:
                continue
            content = str(row.get("报告摘要") or row.get("摘要") or row.get("summary") or "")
            docs.append(self._document(
                document_type="research_report",
                title=title,
                content=content,
                source=str(row.get("机构") or row.get("机构名称") or "东方财富研报"),
                url=str(row.get("报告链接") or row.get("链接") or row.get("url") or ""),
                published_at=_parse_dt(row.get("发布日期") or row.get("发布时间") or row.get("date") or row.get("时间")),
                symbols=[symbol],
                data_source="akshare_research_report",
                metadata={"rating": str(row.get("评级") or row.get("投资评级") or "")},
            ))
        return docs

    def _document(
        self,
        *,
        document_type: str,
        title: str,
        content: str,
        source: str,
        url: str,
        published_at: datetime,
        symbols: List[str],
        data_source: str,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        text = f"{title} {content}"
        score = _sentiment_score(text)
        themes = self._match_themes(text)
        source_weight = SOURCE_WEIGHTS.get(source, SOURCE_WEIGHTS.get(data_source, 1.0))
        influence = min(100.0, 42 + len(content) / 28 + len(themes) * 6 + source_weight * 8)
        doc_key = hashlib.sha1(f"{url}|{title}|{published_at.isoformat()}|{source}".encode("utf-8")).hexdigest()
        return {
            "doc_key": doc_key,
            "document_type": document_type,
            "title": title,
            "content": content,
            "summary": content[:260],
            "source": source,
            "data_source": data_source,
            "url": url,
            "published_at": published_at,
            "ingested_at": datetime.utcnow(),
            "symbols": [item for item in symbols if item],
            "themes": themes,
            "sentiment": _sentiment_label(score),
            "sentiment_score": score,
            "source_weight": source_weight,
            "influence_score": round(influence, 2),
            "metadata": metadata,
        }

    def _save_documents(self, db, documents: List[Dict[str, Any]]) -> int:
        if not documents:
            return 0
        operations = [
            ReplaceOne({"doc_key": doc["doc_key"]}, doc, upsert=True)
            for doc in documents
        ]
        try:
            result = db.market_documents.bulk_write(operations, ordered=False)
            return int(result.upserted_count + result.modified_count)
        except BulkWriteError as e:
            return max(0, len(operations) - len(e.details.get("writeErrors", [])))

    def _format_context(
        self,
        *,
        code: str,
        company_name: str,
        docs: List[Dict[str, Any]],
        events: List[Dict[str, Any]],
        signal: Optional[Dict[str, Any]],
        latest_run: Optional[Dict[str, Any]],
        hours: int,
        max_chars: int,
    ) -> str:
        news_docs = [doc for doc in docs if doc.get("document_type") in {"news", "stock_news", "announcement"}]
        comments = [doc for doc in docs if doc.get("document_type") == "social_comment"]
        reports = [doc for doc in docs if doc.get("document_type") == "research_report"]
        latest_doc = max([_parse_dt(doc.get("published_at")) for doc in docs] or [None])
        latest_run_at = _parse_dt(latest_run.get("ended_at")) if latest_run else None
        sentiment_avg = sum(_safe_float(doc.get("sentiment_score")) for doc in docs) / max(len(docs), 1)

        lines = [
            "## 滚动市场情报证据包",
            f"- 股票: {company_name or code}({code})",
            f"- 时间窗: 最近 {hours} 小时；证据 {len(docs)} 条，新闻/公告 {len(news_docs)}，评论 {len(comments)}，研报 {len(reports)}，全球事件 {len(events)}",
            f"- 最新证据时间: {latest_doc.strftime('%Y-%m-%d %H:%M') if latest_doc else '暂无'}；最近抓取: {latest_run_at.strftime('%Y-%m-%d %H:%M') if latest_run_at else '暂无'}",
            f"- 舆情均值: {sentiment_avg:.2f}（-1悲观，0中性，1乐观）",
        ]
        if signal:
            lines.extend([
                "",
                "### 个股综合信号",
                f"- 综合分: {signal.get('score', '-')}; 强度: {signal.get('signal_strength', '-')}; 主题: {signal.get('theme') or '未分类'}",
                f"- 新闻 {signal.get('news_count', 0)} / 评论 {signal.get('comment_count', 0)} / 研报 {signal.get('research_count', 0)} / 公告 {signal.get('announcement_count', 0)} / 量化 {signal.get('quant_count', 0)}",
            ])
        lines.extend(["", "### 最新新闻/公告"])
        lines.extend(self._format_doc_lines(news_docs[:14]))
        lines.extend(["", "### 研报和券商观点"])
        lines.extend(self._format_doc_lines(reports[:8]))
        lines.extend(["", "### 股吧和投资者评论"])
        lines.extend(self._format_doc_lines(comments[:12]))
        lines.extend(["", "### 全球事件和产业链映射"])
        if events:
            for event in events[:8]:
                lines.append(
                    f"- [{self._fmt_time(event.get('published_at'))}] 严重度{round(_safe_float(event.get('severity')))} "
                    f"{event.get('location_name') or event.get('region')}: {event.get('title')}；"
                    f"传导: {'、'.join(event.get('transmission_channels') or [])}；"
                    f"A股主题: {'、'.join(event.get('mapped_themes') or [])}"
                )
        else:
            lines.append("- 暂无直接映射事件，需结合主题热度和资金确认。")
        lines.extend([
            "",
            "### 使用要求",
            "- 分析时必须显式区分：已证实新闻、投资者讨论、研报观点、全球事件推导、量价/资金确认。",
            "- 舆情只作为可交易假设，不得替代价格确认；若舆情升温但资金/量价背离，必须列为风险反证。",
            "- 若最新证据超过15分钟，应说明时效性风险；若事件严重但未映射到公司业务，应降低结论置信度。",
        ])
        text = "\n".join(lines)
        return text[:max_chars]

    def _format_doc_lines(self, docs: List[Dict[str, Any]]) -> List[str]:
        if not docs:
            return ["- 暂无。"]
        lines = []
        for doc in docs:
            lines.append(
                f"- [{self._fmt_time(doc.get('published_at'))}] [{doc.get('source')}] "
                f"[{doc.get('sentiment')}] 影响{round(_safe_float(doc.get('influence_score')))} "
                f"{doc.get('title')} -- {doc.get('summary') or doc.get('content', '')[:120]}"
            )
        return lines

    def _fmt_time(self, value: Any) -> str:
        dt = _parse_dt(value)
        return dt.strftime("%m-%d %H:%M")

    def _themes_from_documents(self, docs: List[Dict[str, Any]]) -> List[str]:
        themes: List[str] = []
        for doc in docs:
            for theme in doc.get("themes") or []:
                if theme not in themes:
                    themes.append(theme)
        return themes[:8]

    def _match_themes(self, text: str) -> List[str]:
        text = text or ""
        return [
            theme for theme, keywords in THEME_KEYWORDS.items()
            if any(keyword and keyword.lower() in text.lower() for keyword in keywords)
        ]

    def _extract_articles(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        result = data.get("result") or {}
        section = result.get("cmsArticleWebOld") or {}
        if isinstance(section, list):
            return section
        if isinstance(section, dict):
            for key in ("data", "list", "items"):
                value = section.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return self._find_dict_list(data)

    def _find_dict_list(self, value: Any) -> List[Dict[str, Any]]:
        if isinstance(value, list):
            if value and all(isinstance(item, dict) for item in value):
                return value
            for item in value:
                found = self._find_dict_list(item)
                if found:
                    return found
        if isinstance(value, dict):
            for item in value.values():
                found = self._find_dict_list(item)
                if found:
                    return found
        return []

    def _clean_html(self, value: str) -> str:
        return html.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()


_market_evidence_service: Optional[MarketEvidenceService] = None


def get_market_evidence_service() -> MarketEvidenceService:
    global _market_evidence_service
    if _market_evidence_service is None:
        _market_evidence_service = MarketEvidenceService()
    return _market_evidence_service
