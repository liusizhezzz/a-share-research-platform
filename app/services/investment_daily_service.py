"""
Investment daily report service.

Builds a lightweight pre-market report from market news, international
headlines, public comments, quant signal files, favorites, and cached quotes.
All external sources are best-effort so a single crawler failure never blocks
report generation.
"""
from __future__ import annotations

import asyncio
import csv
import hashlib
import html
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import httpx
from bson import ObjectId

from app.core.config import settings
from app.core.database import get_mongo_db
from app.services.news_data_service import get_news_data_service
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


CN_TZ = "Asia/Shanghai"


POSITIVE_WORDS = {
    "增长", "上涨", "走强", "突破", "利好", "盈利", "创新高", "超预期", "回暖", "扩产",
    "中标", "订单", "回购", "增持", "降本", "复苏", "放量", "景气", "涨停", "强势",
}
NEGATIVE_WORDS = {
    "下跌", "走弱", "风险", "亏损", "减持", "立案", "处罚", "暴跌", "低迷", "不及预期",
    "裁员", "停产", "退市", "债务", "违约", "监管", "制裁", "冲突", "关税", "减产",
}


THEME_KEYWORDS: Dict[str, List[str]] = {
    "AI算力": ["AI", "人工智能", "大模型", "算力", "数据中心", "服务器", "液冷", "GPU"],
    "半导体": ["半导体", "芯片", "晶圆", "光刻", "封测", "存储", "国产替代"],
    "机器人": ["机器人", "人形机器人", "减速器", "伺服", "传感器", "自动化"],
    "新能源": ["新能源", "光伏", "储能", "锂电", "电池", "风电", "充电桩"],
    "军工安全": ["军工", "国防", "卫星", "低空", "无人机", "商业航天", "安全"],
    "医药医疗": ["医药", "创新药", "医疗器械", "医保", "疫苗", "CXO"],
    "消费出海": ["消费", "出海", "跨境", "品牌", "白酒", "家电", "旅游"],
    "资源通胀": ["黄金", "有色", "铜", "稀土", "原油", "煤炭", "涨价"],
    "金融地产": ["证券", "券商", "银行", "保险", "地产", "并购重组"],
}

GLOBAL_KEYWORDS = [
    "国际局势", "美联储", "美元", "美债", "中美", "关税", "制裁", "俄乌", "中东",
    "原油", "黄金", "汇率", "出口", "贸易", "地缘",
]

MARKET_KEYWORDS = [
    "A股", "沪深", "创业板", "科创板", "北向资金", "成交额", "政策", "板块",
    "人工智能", "半导体", "机器人", "新能源", "军工", "黄金",
]


@dataclass
class SourceStatus:
    name: str
    ok: bool
    count: int = 0
    message: str = ""


@dataclass
class Candidate:
    code: str
    name: str = ""
    score: float = 0.0
    source: str = ""
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


def _utc_now() -> datetime:
    return datetime.utcnow()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, str):
            cleaned = value.strip().replace(",", "").replace("%", "")
            if cleaned in {"", "-", "None", "nan"}:
                return default
            return float(cleaned)
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(_safe_float(value, default))
    except Exception:
        return default


def _normalize_code(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    text = text.replace(".SH", "").replace(".SZ", "").replace(".SS", "")
    text = text.replace("SH", "").replace("SZ", "")
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 6:
        return digits[-6:]
    if digits:
        return digits.zfill(6)
    return None


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if value is None:
        return _utc_now()
    text = str(value).strip()
    if not text:
        return _utc_now()
    text = text.replace("T", " ").replace("Z", "")
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(text[: len(fmt)], fmt)
        except Exception:
            continue
    return _utc_now()


def _sentiment_score(text: str) -> float:
    text = text or ""
    positive = sum(1 for word in POSITIVE_WORDS if word in text)
    negative = sum(1 for word in NEGATIVE_WORDS if word in text)
    if positive == negative == 0:
        return 0.0
    return max(-1.0, min(1.0, (positive - negative) / max(positive + negative, 1)))


def _sentiment_label(score: float) -> str:
    if score >= 0.25:
        return "positive"
    if score <= -0.25:
        return "negative"
    return "neutral"


def _jsonable(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(val) for key, val in value.items()}
    return value


class InvestmentDailyService:
    """Generate and persist pre-market investment daily reports."""

    def __init__(self) -> None:
        self._indexes_ready = False

    @property
    def db(self):
        return get_mongo_db()

    @property
    def collection(self):
        return self.db.investment_daily_reports

    async def _ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        await self.collection.create_index([("report_date", -1)], unique=True, background=True)
        await self.collection.create_index([("generated_at", -1)], background=True)
        await self.db.investment_daily_source_runs.create_index(
            [("created_at", -1)], background=True
        )
        self._indexes_ready = True

    async def get_latest_report(self) -> Optional[Dict[str, Any]]:
        await self._ensure_indexes()
        doc = await self.collection.find_one(sort=[("report_date", -1), ("generated_at", -1)])
        return _jsonable(doc) if doc else None

    async def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        await self._ensure_indexes()
        cursor = self.collection.find({}, {"markdown": 0}).sort("generated_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        return _jsonable(docs)

    async def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        await self._ensure_indexes()
        query: Dict[str, Any]
        if ObjectId.is_valid(report_id):
            query = {"_id": ObjectId(report_id)}
        else:
            query = {"report_date": report_id}
        doc = await self.collection.find_one(query)
        return _jsonable(doc) if doc else None

    async def generate_daily_report(
        self,
        *,
        report_date: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Generate or return today's report."""
        await self._ensure_indexes()
        local_now = now_tz()
        report_date = report_date or local_now.strftime("%Y-%m-%d")

        if not force_refresh:
            existing = await self.collection.find_one({"report_date": report_date})
            if existing:
                return _jsonable(existing)

        source_statuses: List[SourceStatus] = []

        candidates = await self._load_candidates(source_statuses)
        candidate_codes = [c.code for c in candidates[: settings.INVESTMENT_DAILY_MAX_STOCKS]]

        market_news = await self._collect_market_news(source_statuses)
        international_news = [
            item for item in market_news
            if self._matches_keywords(item.get("title", "") + item.get("content", ""), GLOBAL_KEYWORDS)
        ]
        stock_news = await self._collect_stock_news(candidate_codes, source_statuses)
        guba_posts = await self._collect_guba_posts(candidate_codes[:8], source_statuses)
        rolling = await self._load_rolling_evidence(candidate_codes, source_statuses)
        market_news.extend(rolling.get("market_news", []))
        stock_news.extend(rolling.get("stock_news", []))
        guba_posts.extend(rolling.get("social_comments", []))
        quotes = await self._load_quotes(candidate_codes)
        basics = await self._load_basic_info(candidate_codes)

        all_news = self._dedupe_items(market_news + stock_news, key_fields=("url", "title"))
        all_news.sort(key=lambda item: _parse_dt(item.get("publish_time")), reverse=True)
        directions = self._rank_directions(all_news)
        stock_picks = self._rank_stocks(candidates, quotes, basics, stock_news, guba_posts, directions)
        event_clusters = self._build_event_clusters_for_report(all_news, stock_news, guba_posts)

        report = {
            "report_date": report_date,
            "generated_at": _utc_now(),
            "title": f"{report_date} 开盘前投资日报",
            "status": "ready",
            "summary": self._build_summary(all_news, international_news, directions, stock_picks),
            "market_temperature": self._market_temperature(all_news, quotes),
            "directions": directions,
            "stocks": stock_picks,
            "market_news": all_news[:40],
            "international_news": international_news[:15],
            "event_clusters": event_clusters[:20],
            "social_comments": guba_posts[:30],
            "strategy_inputs": [candidate.__dict__ for candidate in candidates[:30]],
            "sources": [status.__dict__ for status in source_statuses],
            "risk_warnings": self._build_risk_warnings(international_news, all_news),
            "markdown": "",
            "version": 1,
        }
        report["markdown"] = self._render_markdown(report)

        await self._persist_news(all_news)
        await self._persist_social(guba_posts)

        result = await self.collection.replace_one(
            {"report_date": report_date},
            report,
            upsert=True,
        )
        saved = await self.collection.find_one({"report_date": report_date})

        await self.db.investment_daily_source_runs.insert_one({
            "created_at": _utc_now(),
            "report_date": report_date,
            "upserted_id": str(result.upserted_id) if result.upserted_id else None,
            "sources": [status.__dict__ for status in source_statuses],
            "news_count": len(all_news),
            "stock_count": len(stock_picks),
        })

        return _jsonable(saved or report)

    async def preanalyze_report_candidates(
        self,
        report_id: str,
        *,
        user_id: str,
        limit: int = 8,
    ) -> Dict[str, Any]:
        """Submit TradingAgents analysis tasks for the top daily candidates."""
        report = await self.get_report(report_id)
        if not report:
            raise ValueError("investment daily report not found")
        stocks = report.get("stocks") or []
        selected = stocks[: max(1, min(limit, 10))]
        if not selected:
            return {"status": "empty", "task_ids": [], "mapping": []}

        from app.models.analysis import AnalysisParameters, SingleAnalysisRequest
        from app.services.simple_analysis_service import get_simple_analysis_service

        service = get_simple_analysis_service()
        task_ids: List[str] = []
        mapping: List[Dict[str, Any]] = []
        parameters = AnalysisParameters(
            market_type="A股",
            research_depth="标准",
            selected_analysts=["market", "fundamentals", "news", "social"],
            include_sentiment=True,
            include_risk=True,
            language="zh-CN",
            quick_analysis_model="qwen3.7-plus",
            deep_analysis_model="qwen3.7-max",
        )

        async def run_one(task_id: str, req: SingleAnalysisRequest) -> None:
            try:
                await service.execute_analysis_background(task_id, user_id, req)
            except Exception as e:
                logger.error("日报候选股预分析失败 %s: %s", task_id, e, exc_info=True)

        for stock in selected:
            code = _normalize_code(stock.get("code"))
            if not code:
                continue
            req = SingleAnalysisRequest(symbol=code, stock_code=code, parameters=parameters)
            created = await service.create_analysis_task(user_id, req)
            task_id = created.get("task_id")
            if not task_id:
                continue
            task_ids.append(task_id)
            mapping.append({
                "code": code,
                "name": stock.get("name"),
                "task_id": task_id,
                "status": "submitted",
            })
            asyncio.create_task(run_one(task_id, req))

        await self.collection.update_one(
            {"_id": ObjectId(report["_id"])} if ObjectId.is_valid(str(report.get("_id"))) else {"report_date": report.get("report_date")},
            {"$set": {"preanalysis": {"submitted_at": _utc_now(), "task_ids": task_ids, "mapping": mapping}}},
        )
        return {"status": "submitted", "task_ids": task_ids, "mapping": mapping, "count": len(task_ids)}

    async def _load_candidates(self, statuses: List[SourceStatus]) -> List[Candidate]:
        merged: Dict[str, Candidate] = {}

        for candidate in await self._load_strategy_signal_files(statuses):
            merged[candidate.code] = candidate

        for candidate in await self._load_favorites(statuses):
            if candidate.code not in merged:
                merged[candidate.code] = candidate
            else:
                merged[candidate.code].source += "+自选"
                merged[candidate.code].score += 5

        for candidate in await self._load_market_leaders(statuses):
            if candidate.code not in merged:
                merged[candidate.code] = candidate
            else:
                merged[candidate.code].source += "+行情"
                merged[candidate.code].score += min(10, candidate.score)

        values = list(merged.values())
        values.sort(key=lambda item: item.score, reverse=True)
        return values[: max(settings.INVESTMENT_DAILY_MAX_STOCKS * 2, 20)]

    async def _load_strategy_signal_files(self, statuses: List[SourceStatus]) -> List[Candidate]:
        directory = Path(settings.INVESTMENT_DAILY_SIGNAL_DIR)
        if not directory.exists():
            statuses.append(SourceStatus("quant_signal_files", False, 0, f"{directory} 不存在"))
            return []

        files = sorted(directory.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            statuses.append(SourceStatus("quant_signal_files", False, 0, "没有 CSV 信号文件"))
            return []

        candidates: List[Candidate] = []
        latest_files = files[:3]
        for path in latest_files:
            try:
                with path.open("r", encoding="utf-8-sig", newline="") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        code = self._first_code(row)
                        if not code:
                            continue
                        score = self._first_score(row)
                        candidates.append(Candidate(
                            code=code,
                            name=self._first_text(row, ["name", "stock_name", "股票名称", "简称"]),
                            score=score,
                            source=f"量化信号:{path.name}",
                            reason=self._first_text(row, ["reason", "理由", "signal", "tag"]) or "来自量化策略信号",
                            metadata={k: v for k, v in row.items() if v not in (None, "")},
                        ))
            except Exception as e:
                logger.warning("读取量化信号文件失败 %s: %s", path, e)

        candidates.sort(key=lambda item: item.score, reverse=True)
        statuses.append(SourceStatus("quant_signal_files", bool(candidates), len(candidates), ",".join(p.name for p in latest_files)))
        return candidates[: settings.INVESTMENT_DAILY_MAX_STOCKS]

    async def _load_favorites(self, statuses: List[SourceStatus]) -> List[Candidate]:
        try:
            docs = await self.db.user_favorites.find({}).to_list(length=20)
            candidates: List[Candidate] = []
            for doc in docs:
                for fav in doc.get("favorites", []):
                    code = _normalize_code(fav.get("stock_code"))
                    if not code:
                        continue
                    candidates.append(Candidate(
                        code=code,
                        name=fav.get("stock_name", ""),
                        score=30.0,
                        source="自选股",
                        reason=fav.get("notes") or "来自用户自选股",
                        metadata={"tags": fav.get("tags", [])},
                    ))
            statuses.append(SourceStatus("favorites", bool(candidates), len(candidates), "读取用户自选股"))
            return candidates
        except Exception as e:
            statuses.append(SourceStatus("favorites", False, 0, str(e)))
            return []

    async def _load_market_leaders(self, statuses: List[SourceStatus]) -> List[Candidate]:
        try:
            cursor = self.db.market_quotes.find(
                {"pct_chg": {"$ne": None}},
                {"code": 1, "name": 1, "pct_chg": 1, "amount": 1},
            ).sort("pct_chg", -1).limit(30)
            docs = await cursor.to_list(length=30)
            candidates: List[Candidate] = []
            for row in docs:
                code = _normalize_code(row.get("code"))
                if not code:
                    continue
                pct = _safe_float(row.get("pct_chg"))
                amount = _safe_float(row.get("amount"))
                if pct >= 9.6:
                    continue
                momentum = max(0.0, 12 - abs(pct - 3.2) * 2.2)
                liquidity = min(amount / 1_000_000_000, 14)
                price_in_penalty = max(0.0, pct - 6.5) * 2.5
                candidates.append(Candidate(
                    code=code,
                    name=str(row.get("name") or ""),
                    score=28 + momentum + liquidity - price_in_penalty,
                    source="预测候选:量价活跃",
                    reason=f"涨跌幅 {pct:.2f}% 且成交额活跃，作为下一开盘观察候选而非单纯涨幅榜",
                    metadata={
                        "pct_chg": pct,
                        "amount": amount,
                        "momentum_component": round(momentum, 2),
                        "liquidity_component": round(liquidity, 2),
                        "price_in_penalty": round(price_in_penalty, 2),
                    },
                ))
            statuses.append(SourceStatus("market_quotes", bool(candidates), len(candidates), "按量价结构选取下一开盘候选，过滤一字涨停和过热标的"))
            return candidates
        except Exception as e:
            statuses.append(SourceStatus("market_quotes", False, 0, str(e)))
            return []

    async def _load_rolling_evidence(self, codes: List[str], statuses: List[SourceStatus]) -> Dict[str, List[Dict[str, Any]]]:
        """Load the shared rolling evidence pool generated by market intelligence."""
        try:
            cutoff = _utc_now() - timedelta(hours=settings.INVESTMENT_DAILY_HOURS_BACK)
            query = {"published_at": {"$gte": cutoff}}
            docs = await self.db.market_documents.find(query).sort("published_at", -1).limit(260).to_list(length=260)
            code_set = set(codes)
            market_news: List[Dict[str, Any]] = []
            stock_news: List[Dict[str, Any]] = []
            social_comments: List[Dict[str, Any]] = []
            for doc in docs:
                doc_type = doc.get("document_type")
                symbols = [_normalize_code(s) for s in (doc.get("symbols") or [])]
                item = {
                    "symbol": symbols[0] if symbols else None,
                    "title": doc.get("title"),
                    "content": doc.get("content") or doc.get("summary") or "",
                    "summary": doc.get("summary") or "",
                    "url": doc.get("url") or "",
                    "source": doc.get("source") or doc.get("data_source") or "滚动证据池",
                    "publish_time": doc.get("published_at"),
                    "category": (doc.get("themes") or ["general"])[0],
                    "sentiment": doc.get("sentiment") or "neutral",
                    "sentiment_score": _safe_float(doc.get("sentiment_score")),
                    "importance": doc.get("importance") or "medium",
                    "keywords": doc.get("themes") or [],
                    "data_source": doc.get("data_source") or "market_documents",
                }
                if doc_type == "social_comment":
                    social_comments.append({
                        "message_id": doc.get("doc_key"),
                        "symbol": item["symbol"],
                        "platform": doc.get("data_source") or "market_documents",
                        "message_type": "post",
                        "content": item["title"] or item["content"],
                        "publish_time": item["publish_time"],
                        "sentiment": item["sentiment"],
                        "sentiment_score": item["sentiment_score"],
                        "importance": item["importance"],
                        "url": item["url"],
                        "author": {"name": item["source"], "verified": False, "influence_score": _safe_float(doc.get("influence_score"))},
                        "engagement": {},
                        "keywords": item["keywords"],
                        "topics": item["keywords"],
                        "data_source": item["data_source"],
                    })
                elif symbols and code_set.intersection(set(symbols)):
                    stock_news.append(item)
                elif doc_type in {"news", "stock_news", "announcement", "research_report"}:
                    market_news.append(item)
            statuses.append(SourceStatus("rolling_market_documents", bool(docs), len(docs), "读取5分钟滚动证据池"))
            return {
                "market_news": self._dedupe_items(market_news, ("url", "title")),
                "stock_news": self._dedupe_items(stock_news, ("url", "title")),
                "social_comments": self._dedupe_items(social_comments, ("url", "content")),
            }
        except Exception as e:
            statuses.append(SourceStatus("rolling_market_documents", False, 0, str(e)))
            return {"market_news": [], "stock_news": [], "social_comments": []}

    def _build_event_clusters_for_report(
        self,
        market_news: List[Dict[str, Any]],
        stock_news: List[Dict[str, Any]],
        social_comments: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}
        for item in market_news + stock_news:
            text = f"{item.get('title', '')} {item.get('content', '')}"
            themes = self._match_themes(text)
            symbol = _normalize_code(item.get("symbol"))
            normalized_title = re.sub(r"\s+", "", str(item.get("title") or ""))[:24]
            basis = f"{symbol or (themes[0] if themes else '')}:{normalized_title}"
            cluster_id = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:18]
            cluster = grouped.setdefault(cluster_id, {
                "cluster_id": cluster_id,
                "title": item.get("title"),
                "summary": item.get("summary") or item.get("content", "")[:160],
                "items": [],
                "symbols": set(),
                "themes": set(),
                "sources": set(),
                "last_published_at": _parse_dt(item.get("publish_time")),
                "sentiment_total": 0.0,
            })
            if len(cluster["items"]) < 8:
                cluster["items"].append(item)
            if symbol:
                cluster["symbols"].add(symbol)
            cluster["themes"].update(themes)
            cluster["sources"].add(item.get("source") or "未知")
            cluster["last_published_at"] = max(cluster["last_published_at"], _parse_dt(item.get("publish_time")))
            cluster["sentiment_total"] += _safe_float(item.get("sentiment_score"))
        result = []
        for cluster in grouped.values():
            count = len(cluster["items"])
            result.append({
                "cluster_id": cluster["cluster_id"],
                "title": cluster["title"],
                "summary": cluster["summary"],
                "items": cluster["items"],
                "item_count": count,
                "symbols": sorted(cluster["symbols"]),
                "themes": sorted(cluster["themes"]),
                "sources": sorted(cluster["sources"]),
                "last_published_at": cluster["last_published_at"],
                "avg_sentiment": round(cluster["sentiment_total"] / max(count, 1), 3),
            })
        result.sort(key=lambda item: _parse_dt(item.get("last_published_at")), reverse=True)
        return result

    async def _collect_market_news(self, statuses: List[SourceStatus]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        max_per_keyword = max(3, settings.INVESTMENT_DAILY_NEWS_LIMIT // max(len(MARKET_KEYWORDS), 1))
        keyword_results = await self._run_limited(
            [self._fetch_eastmoney_search(keyword, max_per_keyword) for keyword in MARKET_KEYWORDS + GLOBAL_KEYWORDS],
            limit=4,
        )
        for result in keyword_results:
            items.extend(result)
        cls_items = await self._fetch_cls_news(settings.INVESTMENT_DAILY_NEWS_LIMIT)
        items.extend(cls_items)
        items = self._filter_recent(self._dedupe_items(items, ("url", "title")), settings.INVESTMENT_DAILY_HOURS_BACK)
        items.sort(key=lambda item: _parse_dt(item.get("publish_time")), reverse=True)
        statuses.append(SourceStatus("eastmoney_cls_market_news", bool(items), len(items), "东方财富搜索 + 财联社快讯"))
        return items[: settings.INVESTMENT_DAILY_NEWS_LIMIT]

    async def _collect_stock_news(self, codes: List[str], statuses: List[SourceStatus]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        results = await self._run_limited(
            [self._fetch_eastmoney_search(code, 8, symbol=code) for code in codes[: settings.INVESTMENT_DAILY_MAX_STOCKS]],
            limit=4,
        )
        for result in results:
            items.extend(result)
        items = self._filter_recent(self._dedupe_items(items, ("url", "title")), settings.INVESTMENT_DAILY_HOURS_BACK)
        statuses.append(SourceStatus("eastmoney_stock_news", bool(items), len(items), "东方财富个股搜索新闻"))
        return items

    async def _collect_guba_posts(self, codes: List[str], statuses: List[SourceStatus]) -> List[Dict[str, Any]]:
        posts: List[Dict[str, Any]] = []
        results = await self._run_limited(
            [self._fetch_guba_posts(code, limit=8) for code in codes],
            limit=3,
        )
        for result in results:
            posts.extend(result)
        posts = self._dedupe_items(posts, ("url", "content"))
        statuses.append(SourceStatus("eastmoney_guba", bool(posts), len(posts), "东方财富股吧公开帖子标题"))
        return posts

    async def _load_quotes(self, codes: List[str]) -> Dict[str, Dict[str, Any]]:
        if not codes:
            return {}
        cursor = self.db.market_quotes.find({"code": {"$in": codes}})
        docs = await cursor.to_list(length=len(codes))
        return {_normalize_code(doc.get("code")) or "": _jsonable(doc) for doc in docs}

    async def _load_basic_info(self, codes: List[str]) -> Dict[str, Dict[str, Any]]:
        if not codes:
            return {}
        cursor = self.db.stock_basic_info.find(
            {"code": {"$in": codes}},
            {"code": 1, "name": 1, "industry": 1, "market": 1, "source": 1, "total_mv": 1, "circ_mv": 1},
        )
        docs = await cursor.to_list(length=len(codes) * 3)
        basics: Dict[str, Dict[str, Any]] = {}
        for doc in docs:
            code = _normalize_code(doc.get("code"))
            if code and code not in basics:
                basics[code] = _jsonable(doc)
        return basics

    async def _fetch_eastmoney_search(
        self,
        keyword: str,
        limit: int,
        *,
        symbol: Optional[str] = None,
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
        headers = {
            "User-Agent": "Mozilla/5.0 TradingAgents-CN/1.0",
            "Referer": "https://so.eastmoney.com/",
        }
        async with httpx.AsyncClient(timeout=10, headers=headers, follow_redirects=True, trust_env=False) as client:
            response = await client.get("https://search-api-web.eastmoney.com/search/jsonp", params=params)
            response.raise_for_status()
            text = response.text.strip()
        if "(" in text and text.endswith(")"):
            text = text[text.find("(") + 1: -1]
        data = json.loads(text)
        articles = self._extract_articles(data)
        items: List[Dict[str, Any]] = []
        for article in articles[:limit]:
            title = html.unescape(re.sub(r"<[^>]+>", "", str(article.get("title", "")))).strip()
            content = html.unescape(re.sub(r"<[^>]+>", "", str(article.get("content", "") or article.get("summary", "")))).strip()
            if not title:
                continue
            score = _sentiment_score(f"{title} {content}")
            items.append({
                "symbol": symbol,
                "title": title,
                "content": content,
                "summary": content[:220],
                "url": str(article.get("url") or article.get("Url") or ""),
                "source": str(article.get("source") or article.get("mediaName") or "东方财富"),
                "publish_time": _parse_dt(article.get("date") or article.get("time") or article.get("showTime")),
                "category": self._classify_category(title + content),
                "sentiment": _sentiment_label(score),
                "sentiment_score": score,
                "importance": self._importance(title + content),
                "keywords": self._extract_matched_keywords(title + content),
                "data_source": "eastmoney_search",
            })
        return items

    async def _fetch_cls_news(self, limit: int) -> List[Dict[str, Any]]:
        headers = {"User-Agent": "Mozilla/5.0 TradingAgents-CN/1.0", "Referer": "https://www.cls.cn/"}
        try:
            async with httpx.AsyncClient(timeout=8, headers=headers, follow_redirects=True, trust_env=False) as client:
                response = await client.get(
                    "https://www.cls.cn/api/sw",
                    params={"app": "CailianpressWeb", "os": "web", "sv": "7.7.5"},
                )
                response.raise_for_status()
                data = response.json()
        except Exception as e:
            logger.debug("财联社快讯获取失败: %s", e)
            return []
        articles = self._find_dict_list(data)
        items: List[Dict[str, Any]] = []
        for article in articles[:limit]:
            title = str(article.get("title") or article.get("brief") or article.get("content") or "").strip()
            if not title:
                continue
            content = str(article.get("content") or article.get("brief") or "")
            score = _sentiment_score(title + content)
            publish_raw = article.get("ctime") or article.get("time") or article.get("modified_time")
            publish_time = datetime.fromtimestamp(publish_raw) if isinstance(publish_raw, (int, float)) and publish_raw > 10_000 else _parse_dt(publish_raw)
            items.append({
                "symbol": None,
                "title": title[:160],
                "content": content,
                "summary": content[:220],
                "url": str(article.get("shareurl") or article.get("url") or "https://www.cls.cn/telegraph"),
                "source": "财联社",
                "publish_time": publish_time,
                "category": self._classify_category(title + content),
                "sentiment": _sentiment_label(score),
                "sentiment_score": score,
                "importance": self._importance(title + content),
                "keywords": self._extract_matched_keywords(title + content),
                "data_source": "cls_telegraph",
            })
        return items

    async def _fetch_guba_posts(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        url = f"https://guba.eastmoney.com/list,{symbol}.html"
        headers = {"User-Agent": "Mozilla/5.0 TradingAgents-CN/1.0", "Referer": "https://guba.eastmoney.com/"}
        try:
            async with httpx.AsyncClient(timeout=8, headers=headers, follow_redirects=True, trust_env=False) as client:
                response = await client.get(url)
                response.raise_for_status()
                text = response.text
        except Exception as e:
            logger.debug("股吧帖子获取失败 %s: %s", symbol, e)
            return []

        posts: List[Dict[str, Any]] = []
        seen: set[str] = set()

        for row in re.findall(r'<tr[^>]*class="[^"]*listitem[^"]*"[^>]*>(.*?)</tr>', text, re.S):
            title_match = re.search(r'<div[^>]*class="title"[^>]*>.*?<a(?P<attrs>[^>]*)>(?P<title>.*?)</a>', row, re.S)
            if not title_match:
                continue
            attrs = title_match.group("attrs")
            href_match = re.search(r'href="([^"]+)"', attrs)
            if not href_match:
                continue
            href = href_match.group(1)
            clean_title = self._clean_html(title_match.group("title"))
            if not clean_title:
                continue
            post_id = self._extract_attr(attrs, "data-postid") or self._guba_id_from_href(href)
            message_id = f"eastmoney_guba:{symbol}:{post_id or clean_title[:40]}"
            if message_id in seen:
                continue
            seen.add(message_id)
            posts.append(self._make_guba_post(
                symbol=symbol,
                post_id=post_id,
                title=clean_title,
                href=href,
                author=self._extract_row_text(row, "author") or "东方财富股吧用户",
                publish_time=self._parse_guba_time(self._extract_row_text(row, "update")),
                views=_safe_int(self._extract_row_text(row, "read")),
                comments=_safe_int(self._extract_row_text(row, "reply")),
            ))
            if len(posts) >= limit:
                return posts

        json_posts = self._extract_guba_json_posts(text, symbol, limit - len(posts))
        for item in json_posts:
            if item["message_id"] in seen:
                continue
            seen.add(item["message_id"])
            posts.append(item)
            if len(posts) >= limit:
                break
        return posts

    def _extract_guba_json_posts(self, text: str, symbol: str, limit: int) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        marker = "var article_list="
        start = text.find(marker)
        if start < 0:
            return []
        try:
            data, _ = json.JSONDecoder().raw_decode(text[start + len(marker):])
        except Exception as e:
            logger.debug("股吧内嵌JSON解析失败 %s: %s", symbol, e)
            return []
        rows = data.get("re") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return []
        posts: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = str(row.get("post_title") or "").strip()
            if not title:
                continue
            post_id = str(row.get("post_id") or "")
            href = f"/news,{symbol},{post_id}.html" if post_id else f"/list,{symbol}.html"
            posts.append(self._make_guba_post(
                symbol=symbol,
                post_id=post_id,
                title=title,
                href=href,
                author=str(row.get("user_nickname") or "东方财富股吧用户"),
                publish_time=_parse_dt(row.get("post_publish_time") or row.get("post_display_time") or row.get("post_last_time")),
                views=_safe_int(row.get("post_click_count")),
                comments=_safe_int(row.get("post_comment_count")),
                likes=_safe_int(row.get("post_like_count")),
            ))
            if len(posts) >= limit:
                break
        return posts

    def _make_guba_post(
        self,
        *,
        symbol: str,
        post_id: Optional[str],
        title: str,
        href: str,
        author: str,
        publish_time: datetime,
        views: int = 0,
        comments: int = 0,
        likes: int = 0,
    ) -> Dict[str, Any]:
        score = _sentiment_score(title)
        keywords = self._extract_matched_keywords(title)
        return {
            "message_id": f"eastmoney_guba:{symbol}:{post_id or hashlib.sha1(title.encode('utf-8')).hexdigest()[:16]}",
            "symbol": symbol,
            "platform": "eastmoney_guba",
            "message_type": "post",
            "content": title,
            "publish_time": publish_time,
            "sentiment": _sentiment_label(score),
            "sentiment_score": score,
            "importance": self._importance(title),
            "url": self._normalize_guba_url(href),
            "author": {"name": author, "verified": False, "influence_score": 0},
            "engagement": {"views": views, "likes": likes, "comments": comments, "shares": 0, "engagement_rate": 0},
            "keywords": keywords,
            "topics": keywords,
            "data_source": "eastmoney_guba",
        }

    def _parse_guba_time(self, text: str) -> datetime:
        text = (text or "").strip()
        if re.match(r"^\d{2}-\d{2}\s+\d{2}:\d{2}$", text):
            local_now = now_tz().replace(tzinfo=None)
            try:
                parsed = datetime.strptime(f"{local_now.year}-{text}", "%Y-%m-%d %H:%M")
                if parsed > local_now + timedelta(days=1):
                    parsed = parsed.replace(year=parsed.year - 1)
                return parsed
            except Exception:
                return _utc_now()
        return _parse_dt(text)

    def _normalize_guba_url(self, href: str) -> str:
        if href.startswith("//"):
            return f"https:{href}"
        if href.startswith("http://") or href.startswith("https://"):
            return href
        if href.startswith("/"):
            return f"https://guba.eastmoney.com{href}"
        return f"https://guba.eastmoney.com/{href.lstrip('/')}"

    def _guba_id_from_href(self, href: str) -> Optional[str]:
        for pattern in (r"news,[^,]+,(\d+)\.html", r"/news/(\d+)"):
            match = re.search(pattern, href)
            if match:
                return match.group(1)
        return None

    def _extract_attr(self, attrs: str, name: str) -> str:
        match = re.search(rf'{re.escape(name)}="([^"]*)"', attrs)
        return html.unescape(match.group(1)).strip() if match else ""

    def _extract_row_text(self, row: str, class_name: str) -> str:
        match = re.search(rf'<div[^>]*class="{re.escape(class_name)}"[^>]*>(.*?)</div>', row, re.S)
        return self._clean_html(match.group(1)) if match else ""

    def _clean_html(self, value: str) -> str:
        return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", value or ""))).strip()

    def _rank_directions(self, news_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        directions: List[Dict[str, Any]] = []
        for theme, keywords in THEME_KEYWORDS.items():
            matched = []
            sentiment_total = 0.0
            for item in news_items:
                text = f"{item.get('title', '')} {item.get('content', '')}"
                if self._matches_keywords(text, keywords):
                    matched.append(item)
                    sentiment_total += _safe_float(item.get("sentiment_score"))
            if not matched:
                continue
            score = len(matched) * 10 + sentiment_total * 8
            directions.append({
                "name": theme,
                "score": round(score, 2),
                "heat": len(matched),
                "sentiment_score": round(sentiment_total / max(len(matched), 1), 3),
                "keywords": keywords[:5],
                "headlines": [item.get("title", "") for item in matched[:4]],
            })
        directions.sort(key=lambda item: item["score"], reverse=True)
        return directions[:8]

    def _rank_stocks(
        self,
        candidates: List[Candidate],
        quotes: Dict[str, Dict[str, Any]],
        basics: Dict[str, Dict[str, Any]],
        stock_news: List[Dict[str, Any]],
        guba_posts: List[Dict[str, Any]],
        directions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        direction_names = [d["name"] for d in directions[:4]]
        results: List[Dict[str, Any]] = []
        for candidate in candidates:
            code = candidate.code
            q = quotes.get(code, {})
            basic = basics.get(code, {})
            related_news = [item for item in stock_news if item.get("symbol") == code][:8]
            related_posts = [item for item in guba_posts if item.get("symbol") == code][:8]
            news_sentiment = sum(_safe_float(n.get("sentiment_score")) for n in related_news)
            social_sentiment = sum(_safe_float(p.get("sentiment_score")) for p in related_posts)
            pct = _safe_float(q.get("pct_chg"))
            amount = _safe_float(q.get("amount"))
            theme_bonus = 0.0
            text = " ".join([n.get("title", "") for n in related_news] + [candidate.reason])
            for direction in direction_names:
                if direction in text:
                    theme_bonus += 5.0
            price_in_penalty = max(0.0, pct - 6.5) * 3.0
            quant_component = min(candidate.score, 60)
            momentum_component = max(min(pct, 6), -4) * 1.5
            liquidity_component = min(amount / 1_000_000_000, 8)
            news_component = news_sentiment * 8
            social_component = social_sentiment * 4
            score = (
                quant_component
                + momentum_component
                + liquidity_component
                + news_component
                + social_component
                + theme_bonus
                - price_in_penalty
            )
            results.append({
                "code": code,
                "name": candidate.name or basic.get("name") or q.get("name") or code,
                "score": round(max(0.0, min(100.0, score)), 2),
                "source": candidate.source,
                "reason": candidate.reason,
                "industry": basic.get("industry") or basic.get("market") or "-",
                "price": q.get("close"),
                "pct_chg": pct,
                "amount": amount,
                "news_sentiment": round(news_sentiment, 3),
                "social_sentiment": round(social_sentiment, 3),
                "news_count": len(related_news),
                "comment_count": len(related_posts),
                "headlines": [n.get("title", "") for n in related_news[:3]],
                "comments": [p.get("content", "") for p in related_posts[:3]],
                "prediction_horizon": "下一次开盘至未来1-3个交易日",
                "price_in_penalty": round(price_in_penalty, 2),
                "score_breakdown": {
                    "formula": "量化/候选来源 + 量价结构 + 成交额 + 新闻情绪 + 评论情绪 + 主题加成 - price-in惩罚",
                    "input_values": {
                        "quant_component": round(quant_component, 2),
                        "momentum_component": round(momentum_component, 2),
                        "liquidity_component": round(liquidity_component, 2),
                        "news_component": round(news_component, 2),
                        "social_component": round(social_component, 2),
                        "theme_bonus": round(theme_bonus, 2),
                        "price_in_penalty": round(price_in_penalty, 2),
                    },
                    "normalization_method": "涨幅超过6.5%开始price-in扣分；涨停/过热标的在候选源头过滤",
                },
            })
        results.sort(key=lambda item: item["score"], reverse=True)
        return results[: settings.INVESTMENT_DAILY_MAX_STOCKS]

    def _build_summary(
        self,
        news_items: List[Dict[str, Any]],
        international_news: List[Dict[str, Any]],
        directions: List[Dict[str, Any]],
        stocks: List[Dict[str, Any]],
    ) -> str:
        positive = sum(1 for item in news_items if item.get("sentiment") == "positive")
        negative = sum(1 for item in news_items if item.get("sentiment") == "negative")
        top_direction = directions[0]["name"] if directions else "暂无明确主线"
        top_stock = f"{stocks[0]['name']}({stocks[0]['code']})" if stocks else "暂无"
        global_flag = "国际变量偏多" if len(international_news) >= 5 else "国际变量有限"
        tone = "偏积极" if positive > negative else "偏谨慎" if negative > positive else "中性"
        return f"新闻情绪{tone}，主线热度集中在{top_direction}；{global_flag}。综合量化/新闻/评论，首位关注为{top_stock}。"

    def _market_temperature(self, news_items: List[Dict[str, Any]], quotes: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        sentiment = sum(_safe_float(item.get("sentiment_score")) for item in news_items)
        avg_pct = 0.0
        if quotes:
            avg_pct = sum(_safe_float(q.get("pct_chg")) for q in quotes.values()) / max(len(quotes), 1)
        breadth_component = max(0, min(100, 50 + avg_pct * 5))
        news_component = max(0, min(100, 50 + sentiment * 1.5))
        activity_component = max(0, min(100, 35 + len(news_items) * 1.2))
        score = max(0, min(100, breadth_component * 0.35 + news_component * 0.35 + activity_component * 0.30))
        return {
            "score": round(score, 1),
            "label": "热" if score >= 65 else "冷" if score <= 40 else "中性",
            "news_count": len(news_items),
            "avg_candidate_pct_chg": round(avg_pct, 2),
            "score_breakdown": {
                "formula": "35%候选平均涨跌幅广度 + 35%新闻情绪 + 30%新闻活跃度",
                "input_values": {
                    "breadth_component": round(breadth_component, 2),
                    "news_component": round(news_component, 2),
                    "activity_component": round(activity_component, 2),
                    "raw_sentiment_sum": round(sentiment, 3),
                    "avg_candidate_pct_chg": round(avg_pct, 2),
                },
                "normalization_method": "各项先映射到0-100后加权；不是简单按新闻数量打满分",
            },
        }

    def _build_risk_warnings(self, international_news: List[Dict[str, Any]], news_items: List[Dict[str, Any]]) -> List[str]:
        warnings = [
            "日报为研究辅助，不构成投资建议；开盘竞价、流动性和仓位纪律优先。",
            "新闻和股吧数据存在噪声，需结合成交额、公告原文和策略回测结果二次确认。",
        ]
        if any(item.get("sentiment") == "negative" for item in international_news[:8]):
            warnings.append("国际新闻中存在负面变量，注意汇率、商品价格和出口链波动。")
        if sum(1 for item in news_items if item.get("sentiment") == "negative") >= 5:
            warnings.append("近 24 小时负面标题较多，追高需要降低仓位或等待确认。")
        return warnings

    def _render_markdown(self, report: Dict[str, Any]) -> str:
        lines = [
            f"# {report['title']}",
            "",
            f"生成时间：{_jsonable(report['generated_at'])}",
            "",
            f"## 一句话结论\n{report['summary']}",
            "",
            "## 热门方向",
        ]
        for item in report["directions"][:6]:
            lines.append(f"- {item['name']}：热度 {item['heat']}，评分 {item['score']}，情绪 {item['sentiment_score']}")
        lines.append("")
        lines.append("## 下一阶段股票候选")
        for item in report["stocks"]:
            lines.append(
                f"- {item['name']}({item['code']})：预测分 {item['score']}，涨跌幅 {item['pct_chg']:.2f}%，"
                f"price-in惩罚 {item.get('price_in_penalty', 0)}；来源 {item['source']}；理由：{item['reason']}"
            )
        lines.append("")
        lines.append("## 新闻事件簇")
        for cluster in report.get("event_clusters", [])[:8]:
            lines.append(
                f"- {cluster.get('title')}：{cluster.get('item_count', 0)}条，主题 {', '.join(cluster.get('themes') or []) or '未分类'}"
            )
        lines.append("")
        lines.append("## 国际与宏观线索")
        for item in report["international_news"][:8]:
            lines.append(f"- {item.get('title')}（{item.get('source')}）")
        lines.append("")
        lines.append("## 风险提示")
        for warning in report["risk_warnings"]:
            lines.append(f"- {warning}")
        lines.extend([
            "",
            "## 评分方法",
            "- 候选股预测分 = 量化/候选来源 + 量价结构 + 成交额 + 新闻情绪 + 评论情绪 + 主题加成 - price-in惩罚。",
            "- 市场温度 = 35%候选平均涨跌幅广度 + 35%新闻情绪 + 30%新闻活跃度。",
            "- 日报为研究辅助，不构成投资建议；必须等待竞价、量价和风险反证确认。",
        ])
        return "\n".join(lines)

    async def _run_limited(self, coroutines: List[Any], limit: int) -> List[List[Dict[str, Any]]]:
        semaphore = asyncio.Semaphore(limit)

        async def runner(coro):
            async with semaphore:
                try:
                    return await coro
                except Exception as e:
                    logger.debug("日报采集任务失败: %s", e)
                    return []

        if not coroutines:
            return []
        return await asyncio.gather(*(runner(coro) for coro in coroutines))

    async def _persist_news(self, news_items: List[Dict[str, Any]]) -> None:
        try:
            service = await get_news_data_service()
            await service.save_news_data(news_items, "investment_daily", "CN")
        except Exception as e:
            logger.debug("日报新闻入库失败: %s", e)

    async def _persist_social(self, posts: List[Dict[str, Any]]) -> None:
        if not posts:
            return
        try:
            from app.services.social_media_service import get_social_media_service
            service = await get_social_media_service()
            await service.save_social_media_messages(posts)
        except Exception as e:
            logger.debug("日报社媒入库失败: %s", e)

    def _extract_articles(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        try:
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
        except Exception:
            return []

    def _find_dict_list(self, value: Any) -> List[Dict[str, Any]]:
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            return value
        if isinstance(value, dict):
            for child in value.values():
                found = self._find_dict_list(child)
                if found:
                    return found
        return []

    def _filter_recent(self, items: List[Dict[str, Any]], hours_back: int) -> List[Dict[str, Any]]:
        cutoff = _utc_now() - timedelta(hours=hours_back)
        filtered = []
        for item in items:
            publish_time = _parse_dt(item.get("publish_time"))
            if publish_time >= cutoff:
                item["publish_time"] = publish_time
                filtered.append(item)
        return filtered

    def _dedupe_items(self, items: Iterable[Dict[str, Any]], key_fields: Iterable[str]) -> List[Dict[str, Any]]:
        seen = set()
        result = []
        for item in items:
            key = tuple(str(item.get(field, "")).strip() for field in key_fields)
            if not any(key) or key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    def _matches_keywords(self, text: str, keywords: List[str]) -> bool:
        return any(keyword.lower() in text.lower() for keyword in keywords)

    def _match_themes(self, text: str) -> List[str]:
        return [theme for theme, keywords in THEME_KEYWORDS.items() if self._matches_keywords(text or "", keywords)]

    def _extract_matched_keywords(self, text: str) -> List[str]:
        keywords = []
        for words in THEME_KEYWORDS.values():
            for word in words:
                if word.lower() in text.lower() and word not in keywords:
                    keywords.append(word)
        for word in GLOBAL_KEYWORDS:
            if word in text and word not in keywords:
                keywords.append(word)
        return keywords[:10]

    def _classify_category(self, text: str) -> str:
        if self._matches_keywords(text, GLOBAL_KEYWORDS):
            return "global_macro"
        if any(word in text for word in ["公告", "业绩", "年报", "季报", "重组"]):
            return "company_announcement"
        if any(word in text for word in ["政策", "监管", "央行", "会议"]):
            return "policy_news"
        if any(word in text for word in ["板块", "指数", "成交", "资金"]):
            return "market_news"
        return "general"

    def _importance(self, text: str) -> str:
        if any(word in text for word in ["突发", "重大", "紧急", "制裁", "战争", "业绩预告", "重组", "停牌"]):
            return "high"
        if any(word in text for word in ["政策", "监管", "订单", "减持", "增持", "回购", "涨停"]):
            return "medium"
        return "low"

    def _first_code(self, row: Dict[str, Any]) -> Optional[str]:
        for key in ("code", "stock_code", "ts_code", "symbol", "股票代码", "证券代码"):
            code = _normalize_code(row.get(key))
            if code:
                return code
        return None

    def _first_score(self, row: Dict[str, Any]) -> float:
        for key in ("score", "final_score", "rank_score", "prediction", "weight", "综合分", "得分"):
            if key in row and row.get(key) not in (None, ""):
                value = _safe_float(row.get(key))
                if abs(value) <= 1:
                    value *= 100
                return value
        rank = _safe_float(row.get("rank") or row.get("排名"), 50)
        return max(0.0, 60.0 - rank)

    def _first_text(self, row: Dict[str, Any], keys: List[str]) -> str:
        for key in keys:
            value = row.get(key)
            if value:
                return str(value)
        return ""


_investment_daily_service: Optional[InvestmentDailyService] = None


async def get_investment_daily_service() -> InvestmentDailyService:
    global _investment_daily_service
    if _investment_daily_service is None:
        _investment_daily_service = InvestmentDailyService()
    return _investment_daily_service
