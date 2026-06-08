"""
Automated market intelligence service.

This service turns rolling news, comments, research report metadata, global
events, quotes, and quant inputs into dashboard-ready market intelligence.
The first version deliberately reuses the existing investment daily crawlers so
the new dashboard starts with proven data sources instead of a disconnected
mock pipeline.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from bson import ObjectId

from app.core.config import settings
from app.core.database import get_mongo_db
from app.services.investment_daily_service import (
    GLOBAL_KEYWORDS,
    MARKET_KEYWORDS,
    THEME_KEYWORDS,
    Candidate,
    SourceStatus,
    _jsonable,
    _normalize_code,
    _parse_dt,
    _safe_float,
    _sentiment_label,
    _sentiment_score,
    _utc_now,
    get_investment_daily_service,
)
from app.utils.timezone import now_tz

logger = logging.getLogger(__name__)


REPORT_TYPES = {"pre_market", "intraday", "closing", "event_flash", "research_digest"}

EVENT_GEO_RULES: List[Dict[str, Any]] = [
    {
        "keywords": ["霍尔木兹", "伊朗", "波斯湾", "Hormuz"],
        "name": "霍尔木兹海峡风险",
        "lat": 26.56,
        "lon": 56.25,
        "region": "中东",
        "country": "伊朗/阿曼",
        "affected_assets": ["原油", "油运", "航运保险"],
        "transmission_channels": ["能源价格", "运输风险", "通胀预期"],
        "themes": ["资源通胀", "军工安全"],
        "severity_bias": 18,
    },
    {
        "keywords": ["红海", "苏伊士", "也门", "胡塞"],
        "name": "红海/苏伊士航运扰动",
        "lat": 20.3,
        "lon": 38.5,
        "region": "中东/非洲",
        "country": "红海航道",
        "affected_assets": ["集运", "油运", "出口链"],
        "transmission_channels": ["航运价格", "供应链", "保险成本"],
        "themes": ["资源通胀", "消费出海"],
        "severity_bias": 16,
    },
    {
        "keywords": ["巴拿马运河", "Panama"],
        "name": "巴拿马运河通行约束",
        "lat": 9.08,
        "lon": -79.68,
        "region": "拉美",
        "country": "巴拿马",
        "affected_assets": ["航运", "粮食", "能源"],
        "transmission_channels": ["运价", "交付周期", "库存"],
        "themes": ["资源通胀", "消费出海"],
        "severity_bias": 12,
    },
    {
        "keywords": ["马六甲", "南海", "台海"],
        "name": "亚太关键航道风险",
        "lat": 2.6,
        "lon": 101.0,
        "region": "东南亚",
        "country": "马六甲海峡",
        "affected_assets": ["航运", "半导体", "出口链"],
        "transmission_channels": ["供应链", "地缘风险", "贸易预期"],
        "themes": ["半导体", "军工安全", "消费出海"],
        "severity_bias": 14,
    },
    {
        "keywords": ["美联储", "美元", "美债", "FOMC", "CPI", "非农"],
        "name": "美国宏观变量变化",
        "lat": 38.9,
        "lon": -77.03,
        "region": "北美",
        "country": "美国",
        "affected_assets": ["美元", "美债", "黄金", "成长股估值"],
        "transmission_channels": ["利率", "汇率", "风险偏好"],
        "themes": ["金融地产", "资源通胀", "AI算力"],
        "severity_bias": 10,
    },
    {
        "keywords": ["日本央行", "日元", "日本利率"],
        "name": "日本利率/汇率扰动",
        "lat": 35.68,
        "lon": 139.76,
        "region": "亚洲",
        "country": "日本",
        "affected_assets": ["日元", "全球流动性", "出口链"],
        "transmission_channels": ["汇率", "利差", "风险偏好"],
        "themes": ["金融地产", "消费出海"],
        "severity_bias": 8,
    },
    {
        "keywords": ["欧洲央行", "欧元区", "德国", "法国"],
        "name": "欧洲宏观/需求变化",
        "lat": 50.11,
        "lon": 8.68,
        "region": "欧洲",
        "country": "欧元区",
        "affected_assets": ["欧元", "出口需求", "工业品"],
        "transmission_channels": ["外需", "汇率", "制造业订单"],
        "themes": ["消费出海", "新能源", "半导体"],
        "severity_bias": 8,
    },
    {
        "keywords": ["俄乌", "俄罗斯", "乌克兰", "制裁"],
        "name": "俄乌与制裁扰动",
        "lat": 50.45,
        "lon": 30.52,
        "region": "欧洲",
        "country": "乌克兰/俄罗斯",
        "affected_assets": ["原油", "天然气", "粮食", "黄金"],
        "transmission_channels": ["能源供给", "避险", "制裁链"],
        "themes": ["资源通胀", "军工安全"],
        "severity_bias": 18,
    },
    {
        "keywords": ["地震", "火山", "台风", "洪水", "极端天气", "灾害"],
        "name": "自然灾害与供应链扰动",
        "lat": 31.23,
        "lon": 121.47,
        "region": "全球",
        "country": "待定位",
        "affected_assets": ["保险", "农业", "电力", "物流"],
        "transmission_channels": ["供应中断", "重建需求", "成本上升"],
        "themes": ["资源通胀", "医药医疗", "新能源"],
        "severity_bias": 12,
    },
]

HIGH_SEVERITY_WORDS = {
    "封锁", "袭击", "爆炸", "冲突", "战争", "制裁", "断供", "停产", "大涨", "暴涨",
    "暴跌", "地震", "火灾", "台风", "洪水", "紧急", "突发", "危机",
}

SOURCE_WEIGHTS = {
    "财联社": 1.18,
    "证券时报": 1.15,
    "上海证券报": 1.12,
    "每日经济新闻": 1.08,
    "东方财富": 1.0,
    "eastmoney_guba": 0.72,
}

WORLD_MONITOR_LAYERS: List[Dict[str, Any]] = [
    {
        "id": "geopolitics",
        "label": "地缘冲突",
        "description": "战争、制裁、封锁、袭击等高冲击事件",
        "event_types": ["geopolitical"],
        "themes": ["军工安全", "资源通胀"],
        "color": "#ef5b6f",
    },
    {
        "id": "macro_policy",
        "label": "宏观/央行",
        "description": "利率、汇率、美元、美债、通胀和政策预期",
        "event_types": ["macro"],
        "themes": ["金融地产", "资源通胀"],
        "color": "#4f8df7",
    },
    {
        "id": "commodities",
        "label": "商品能源",
        "description": "油气、黄金、铜、煤炭和大宗商品价格扰动",
        "event_types": ["commodity"],
        "themes": ["资源通胀", "新能源"],
        "color": "#f2a84a",
    },
    {
        "id": "chokepoints",
        "label": "关键通道",
        "description": "海峡、运河、港口和航运保险风险",
        "event_types": ["geopolitical", "commodity", "global_news"],
        "themes": ["资源通胀", "消费出海", "军工安全"],
        "color": "#22c7a9",
    },
    {
        "id": "tech_supply_chain",
        "label": "科技供应链",
        "description": "AI、半导体、机器人、新能源和出口限制",
        "event_types": ["global_news"],
        "themes": ["AI算力", "半导体", "机器人", "新能源"],
        "color": "#8b7cf6",
    },
    {
        "id": "natural_hazard",
        "label": "自然灾害",
        "description": "极端天气、地震、火点、洪水及重建需求",
        "event_types": ["natural_disaster"],
        "themes": ["资源通胀", "医药医疗", "新能源"],
        "color": "#35b6ff",
    },
    {
        "id": "a_share_mapping",
        "label": "A股映射",
        "description": "已映射到A股主题或个股的事件",
        "event_types": [],
        "themes": list(THEME_KEYWORDS.keys()),
        "color": "#7bd88f",
    },
]

STRATEGIC_CORRIDORS: List[Dict[str, Any]] = [
    {
        "id": "hormuz",
        "name": "霍尔木兹海峡",
        "region": "中东",
        "lat": 26.56,
        "lon": 56.25,
        "keywords": ["霍尔木兹", "伊朗", "波斯湾", "Hormuz"],
        "exposure": ["原油", "油运", "通胀"],
        "a_share_themes": ["资源通胀", "军工安全"],
        "base_risk": 62,
    },
    {
        "id": "suez_red_sea",
        "name": "红海/苏伊士",
        "region": "中东/非洲",
        "lat": 20.3,
        "lon": 38.5,
        "keywords": ["红海", "苏伊士", "也门", "胡塞"],
        "exposure": ["集运", "油运", "出口链"],
        "a_share_themes": ["资源通胀", "消费出海"],
        "base_risk": 58,
    },
    {
        "id": "malacca",
        "name": "马六甲海峡",
        "region": "东南亚",
        "lat": 2.6,
        "lon": 101.0,
        "keywords": ["马六甲", "南海", "台海"],
        "exposure": ["半导体", "能源进口", "出口链"],
        "a_share_themes": ["半导体", "军工安全", "消费出海"],
        "base_risk": 54,
    },
    {
        "id": "panama",
        "name": "巴拿马运河",
        "region": "拉美",
        "lat": 9.08,
        "lon": -79.68,
        "keywords": ["巴拿马", "Panama"],
        "exposure": ["粮食", "航运", "能源"],
        "a_share_themes": ["资源通胀", "消费出海"],
        "base_risk": 46,
    },
    {
        "id": "taiwan_strait",
        "name": "台海/西太平洋",
        "region": "亚太",
        "lat": 24.0,
        "lon": 121.0,
        "keywords": ["台海", "台湾海峡", "台湾", "南海"],
        "exposure": ["半导体", "军工", "电子供应链"],
        "a_share_themes": ["半导体", "军工安全", "AI算力"],
        "base_risk": 60,
    },
    {
        "id": "bosporus_black_sea",
        "name": "黑海/博斯普鲁斯",
        "region": "欧洲",
        "lat": 41.12,
        "lon": 29.05,
        "keywords": ["黑海", "博斯普鲁斯", "俄乌", "乌克兰", "俄罗斯"],
        "exposure": ["粮食", "天然气", "油运"],
        "a_share_themes": ["资源通胀", "军工安全"],
        "base_risk": 57,
    },
]

SOURCE_ENVELOPE_GROUPS: List[Dict[str, Any]] = [
    {"id": "market_news", "label": "市场新闻", "document_types": ["news", "stock_news"], "max_age_minutes": 15},
    {"id": "social_comments", "label": "股吧评论", "document_types": ["social_comment"], "max_age_minutes": 15},
    {"id": "announcements", "label": "公告元数据", "document_types": ["announcement"], "max_age_minutes": 180},
    {"id": "research_reports", "label": "研报元数据", "document_types": ["research_report"], "max_age_minutes": 720},
    {"id": "quant_signals", "label": "量化信号", "document_types": ["quant_signal"], "max_age_minutes": 1440},
    {"id": "global_events", "label": "全球事件", "event_group": True, "max_age_minutes": 30},
]


@dataclass
class RunCounter:
    source: str
    fetched: int = 0
    saved: int = 0
    failed: int = 0
    latest_publish_time: Optional[datetime] = None
    message: str = ""


class MarketIntelligenceService:
    """Build and query automated market-intelligence snapshots."""

    def __init__(self) -> None:
        self._indexes_ready = False

    @property
    def db(self):
        return get_mongo_db()

    async def _ensure_indexes(self) -> None:
        if self._indexes_ready:
            return

        await self.db.market_documents.create_index(
            [("doc_key", 1)], unique=True, background=True
        )
        await self.db.market_documents.create_index(
            [("published_at", -1), ("document_type", 1)], background=True
        )
        await self.db.market_documents.create_index([("symbols", 1)], background=True)
        await self.db.market_documents.create_index([("themes", 1)], background=True)
        await self.db.global_events.create_index(
            [("event_id", 1)], unique=True, background=True
        )
        await self.db.global_events.create_index([("published_at", -1)], background=True)
        await self.db.global_events.create_index([("severity", -1)], background=True)
        await self.db.theme_signals.create_index(
            [("signal_date", -1), ("theme", 1)], background=True
        )
        await self.db.stock_signals.create_index(
            [("signal_date", -1), ("code", 1)], background=True
        )
        await self.db.market_intelligence_reports.create_index(
            [("generated_at", -1)], background=True
        )
        await self.db.market_intelligence_reports.create_index(
            [("report_date", -1), ("report_type", 1)], background=True
        )
        await self.db.crawler_runs.create_index([("started_at", -1)], background=True)
        await self.db.crawler_runs.create_index([("job_id", 1), ("started_at", -1)], background=True)
        self._indexes_ready = True

    async def ingest_incremental(
        self,
        *,
        job_id: str = "market_data_ingest_interval",
        lookback_minutes: Optional[int] = None,
        lookback_hours: Optional[int] = None,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Ingest recent evidence, update events/signals, and record the run."""
        await self._ensure_indexes()
        started_at = _utc_now()
        window_start = started_at - timedelta(
            hours=lookback_hours if lookback_hours is not None else 0,
            minutes=0 if lookback_hours is not None else (lookback_minutes or settings.MARKET_INTELLIGENCE_INCREMENTAL_WINDOW_MINUTES),
        )
        if force_refresh:
            window_start = started_at - timedelta(hours=settings.MARKET_INTELLIGENCE_FORCE_LOOKBACK_HOURS)

        counters: Dict[str, RunCounter] = {}

        def counter(name: str) -> RunCounter:
            if name not in counters:
                counters[name] = RunCounter(source=name)
            return counters[name]

        documents: List[Dict[str, Any]] = []
        global_events: List[Dict[str, Any]] = []

        try:
            daily = await get_investment_daily_service()
            statuses: List[SourceStatus] = []
            candidates = await daily._load_candidates(statuses)
            if settings.MARKET_INTELLIGENCE_INCLUDE_RECENT_ANALYSIS_STOCKS:
                recent_candidates = await self._load_recent_analysis_candidates(statuses)
                candidates = self._merge_candidates(candidates, recent_candidates)
            codes = [item.code for item in candidates[: settings.MARKET_INTELLIGENCE_MAX_STOCKS]]

            market_news = await daily._collect_market_news(statuses)
            stock_news = await daily._collect_stock_news(codes, statuses)
            guba_posts = await daily._collect_guba_posts(codes[:8], statuses)
            reports = await self._fetch_research_reports(codes[:6])
            announcements = await self._fetch_announcements(daily, codes[:8])

            for status in statuses:
                c = counter(status.name)
                c.fetched += status.count
                c.message = status.message
                if not status.ok:
                    c.failed += 1

            documents.extend(self._normalize_news_documents(market_news, "news", window_start))
            documents.extend(self._normalize_news_documents(stock_news, "stock_news", window_start))
            documents.extend(self._normalize_social_documents(guba_posts, window_start))
            documents.extend(self._normalize_research_documents(reports, window_start))
            documents.extend(self._normalize_news_documents(announcements, "announcement", window_start))
            documents.extend(self._normalize_quant_signal_documents(candidates))

            counter("market_documents").fetched = len(documents)
            counter("announcements").fetched = len(announcements)
            counter("research_reports").fetched = len(reports)
            counter("quant_signal_files").fetched = max(counter("quant_signal_files").fetched, len(candidates))
            global_events = self._extract_global_events(documents, window_start)
            counter("global_events").fetched = len(global_events)

            saved_documents = await self._save_documents(documents)
            saved_events = await self._save_global_events(global_events)
            await self._persist_rolling_sources(daily, market_news, stock_news, announcements, reports, guba_posts)
            counter("market_documents").saved = saved_documents
            counter("global_events").saved = saved_events

            signals = await self._recompute_signals(window_hours=36)
            report = {
                "job_id": job_id,
                "started_at": started_at,
                "ended_at": _utc_now(),
                "status": "ready",
                "lookback_start": window_start,
                "documents_seen": len(documents),
                "documents_saved": saved_documents,
                "events_seen": len(global_events),
                "events_saved": saved_events,
                "theme_count": len(signals.get("themes", [])),
                "stock_count": len(signals.get("stocks", [])),
                "sources": [c.__dict__ for c in counters.values()],
            }
        except Exception as e:
            logger.error("市场情报增量抓取失败: %s", e, exc_info=True)
            report = {
                "job_id": job_id,
                "started_at": started_at,
                "ended_at": _utc_now(),
                "status": "error",
                "lookback_start": window_start,
                "documents_seen": len(documents),
                "documents_saved": 0,
                "events_seen": len(global_events),
                "events_saved": 0,
                "theme_count": 0,
                "stock_count": 0,
                "sources": [c.__dict__ for c in counters.values()],
                "error": str(e),
            }

        await self.db.crawler_runs.insert_one(report)
        return _jsonable(report)

    async def generate_report(
        self,
        *,
        report_type: str = "pre_market",
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        if report_type not in REPORT_TYPES:
            report_type = "pre_market"
        await self._ensure_indexes()

        if force_refresh:
            await self.ingest_incremental(
                job_id=f"{report_type}_force_ingest",
                lookback_hours=settings.MARKET_INTELLIGENCE_FORCE_LOOKBACK_HOURS,
                force_refresh=True,
            )

        dashboard = await self.build_dashboard(hours=36)
        local_now = now_tz()
        report = {
            "report_type": report_type,
            "report_date": local_now.strftime("%Y-%m-%d"),
            "generated_at": _utc_now(),
            "title": self._report_title(report_type, local_now),
            "status": dashboard.get("status", "ready"),
            "summary": dashboard.get("summary", ""),
            "dashboard": dashboard,
            "markdown_report": self._render_markdown_report(report_type, dashboard),
            "version": 1,
        }
        await self.db.market_intelligence_reports.insert_one(report)
        return _jsonable(report)

    async def get_latest_report(self) -> Optional[Dict[str, Any]]:
        await self._ensure_indexes()
        doc = await self.db.market_intelligence_reports.find_one(sort=[("generated_at", -1)])
        if doc:
            return _jsonable(doc)
        dashboard = await self.build_dashboard(hours=36)
        return {
            "report_type": "snapshot",
            "report_date": now_tz().strftime("%Y-%m-%d"),
            "generated_at": None,
            "title": "市场情报快照",
            "status": dashboard.get("status", "partial"),
            "summary": dashboard.get("summary", ""),
            "dashboard": dashboard,
            "markdown_report": dashboard.get("markdown_report", ""),
            "version": 1,
        }

    async def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        await self._ensure_indexes()
        cursor = self.db.market_intelligence_reports.find(
            {}, {"dashboard": 0}
        ).sort("generated_at", -1).limit(limit)
        return _jsonable(await cursor.to_list(length=limit))

    async def build_dashboard(self, *, hours: int = 36) -> Dict[str, Any]:
        await self._ensure_indexes()
        cutoff = _utc_now() - timedelta(hours=hours)
        documents = await self.db.market_documents.find(
            {"published_at": {"$gte": cutoff}}
        ).sort("published_at", -1).limit(300).to_list(length=300)
        events = await self.db.global_events.find(
            {"published_at": {"$gte": cutoff}}
        ).sort("published_at", -1).limit(120).to_list(length=120)
        events = [self._ensure_event_layers(event) for event in events]
        latest_report = await self.db.market_intelligence_reports.find_one(sort=[("generated_at", -1)])
        latest_run = await self.db.crawler_runs.find_one(sort=[("ended_at", -1)])
        crawler_statuses = await self.get_source_status()

        theme_nodes = self._build_theme_heatmap(documents, events)
        stock_opportunities = await self._build_stock_opportunities(documents, theme_nodes)
        industry_matrix = self._build_industry_matrix(theme_nodes)
        event_chains = self._build_event_impact_chains(events, theme_nodes, stock_opportunities)
        risk_warnings = self._build_risk_warnings(events, crawler_statuses)
        map_layers = self._build_map_layers(events, theme_nodes)
        event_feed = self._build_event_feed(events)
        corridor_strip = self._build_corridor_strip(events)
        source_envelopes = self._build_source_envelopes(documents, events)
        high_event = any(_safe_float(event.get("severity")) >= settings.MARKET_INTELLIGENCE_HIGH_SEVERITY_THRESHOLD for event in events)
        source_coverage = self._source_coverage(crawler_statuses)

        summary = self._build_dashboard_summary(theme_nodes, stock_opportunities, events, risk_warnings)
        markdown_report = self._render_dashboard_markdown(summary, theme_nodes, stock_opportunities, event_chains, risk_warnings)

        return _jsonable({
            "status": "ready" if documents or events else "partial",
            "summary": summary,
            "last_ingested_at": latest_run.get("ended_at") if latest_run else None,
            "last_report_generated_at": latest_report.get("generated_at") if latest_report else None,
            "source_coverage": source_coverage,
            "has_high_severity_event": high_event,
            "global_events": events[:80],
            "event_impact_chains": event_chains[:8],
            "map_layers": map_layers,
            "event_feed": event_feed,
            "corridor_strip": corridor_strip,
            "source_envelopes": source_envelopes,
            "theme_heatmap_nodes": theme_nodes,
            "industry_matrix": industry_matrix,
            "stock_opportunities": stock_opportunities[:30],
            "risk_warnings": risk_warnings,
            "crawler_statuses": crawler_statuses,
            "markdown_report": markdown_report,
        })

    async def get_global_events(self, *, hours: int = 36, severity: str = "all") -> List[Dict[str, Any]]:
        await self._ensure_indexes()
        query: Dict[str, Any] = {"published_at": {"$gte": _utc_now() - timedelta(hours=hours)}}
        if severity == "high":
            query["severity"] = {"$gte": settings.MARKET_INTELLIGENCE_HIGH_SEVERITY_THRESHOLD}
        cursor = self.db.global_events.find(query).sort("published_at", -1).limit(200)
        events = await cursor.to_list(length=200)
        return _jsonable([self._ensure_event_layers(event) for event in events])

    async def get_global_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        await self._ensure_indexes()
        doc = await self.db.global_events.find_one({"event_id": event_id})
        if doc:
            doc = self._ensure_event_layers(doc)
        return _jsonable(doc) if doc else None

    async def get_themes(self) -> List[Dict[str, Any]]:
        await self._ensure_indexes()
        cursor = self.db.theme_signals.find({}).sort([("signal_date", -1), ("score", -1)]).limit(60)
        docs = await cursor.to_list(length=60)
        seen = set()
        result = []
        for doc in docs:
            theme = doc.get("theme")
            if theme in seen:
                continue
            seen.add(theme)
            result.append(doc)
        return _jsonable(result)

    async def get_stock_signal(self, code: str) -> Optional[Dict[str, Any]]:
        await self._ensure_indexes()
        clean = _normalize_code(code)
        if not clean:
            return None
        doc = await self.db.stock_signals.find_one({"code": clean}, sort=[("signal_date", -1)])
        if not doc:
            return None
        docs = await self.db.market_documents.find(
            {"symbols": clean}
        ).sort("published_at", -1).limit(40).to_list(length=40)
        doc["documents"] = docs
        return _jsonable(doc)

    async def get_source_status(self) -> List[Dict[str, Any]]:
        await self._ensure_indexes()
        cursor = self.db.crawler_runs.find({}).sort("ended_at", -1).limit(80)
        runs = await cursor.to_list(length=80)
        status_by_source: Dict[str, Dict[str, Any]] = {}
        now = _utc_now()
        for run in runs:
            for source in run.get("sources", []):
                name = source.get("source") or "unknown"
                if name in status_by_source:
                    continue
                ended_at = _parse_dt(run.get("ended_at"))
                lag_minutes = max(0, int((now - ended_at).total_seconds() // 60))
                ok = run.get("status") == "ready" and lag_minutes <= 15
                status_by_source[name] = {
                    "name": name,
                    "ok": ok,
                    "last_success_at": ended_at if run.get("status") == "ready" else None,
                    "last_run_at": ended_at,
                    "lag_minutes": lag_minutes,
                    "fetched": source.get("fetched", 0),
                    "saved": source.get("saved", 0),
                    "failed": source.get("failed", 0),
                    "message": source.get("message") or run.get("error") or "",
                }
        return _jsonable(list(status_by_source.values()))

    async def run_pre_market_enrichment(self) -> Dict[str, Any]:
        return await self.ingest_incremental(
            job_id="pre_market_enrichment",
            lookback_hours=36,
            force_refresh=True,
        )

    async def run_research_report_digest(self) -> Dict[str, Any]:
        await self.ingest_incremental(
            job_id="research_report_digest_ingest",
            lookback_hours=36,
            force_refresh=True,
        )
        return await self.generate_report(report_type="research_digest")

    async def maybe_generate_event_flash(self) -> Optional[Dict[str, Any]]:
        events = await self.get_global_events(hours=2, severity="high")
        if not events:
            return None
        latest = events[0]
        marker = f"event_flash:{latest.get('event_id')}"
        existing = await self.db.market_intelligence_reports.find_one({"event_flash_key": marker})
        if existing:
            return _jsonable(existing)
        report = await self.generate_report(report_type="event_flash")
        await self.db.market_intelligence_reports.update_one(
            {"_id": ObjectId(report["_id"])},
            {"$set": {"event_flash_key": marker}},
        )
        return await self.get_latest_report()

    async def _fetch_research_reports(self, codes: List[str]) -> List[Dict[str, Any]]:
        reports: List[Dict[str, Any]] = []
        if not codes:
            return reports
        try:
            import akshare as ak

            async def fetch_one(code: str) -> List[Dict[str, Any]]:
                try:
                    df = await asyncio.to_thread(ak.stock_research_report_em, symbol=code)
                except TypeError:
                    try:
                        df = await asyncio.to_thread(ak.stock_research_report_em, code)
                    except Exception:
                        return []
                except Exception:
                    return []
                if df is None or getattr(df, "empty", True):
                    return []
                rows = []
                for _, row in df.head(5).iterrows():
                    title = str(row.get("报告名称") or row.get("标题") or row.get("title") or "").strip()
                    if not title:
                        continue
                    publish = row.get("发布日期") or row.get("发布时间") or row.get("date") or row.get("时间")
                    rows.append({
                        "symbol": code,
                        "title": title,
                        "content": str(row.get("报告摘要") or row.get("摘要") or row.get("summary") or ""),
                        "source": str(row.get("机构") or row.get("机构名称") or row.get("source") or "东方财富研报"),
                        "url": str(row.get("报告链接") or row.get("链接") or row.get("url") or ""),
                        "publish_time": _parse_dt(publish),
                        "rating": str(row.get("评级") or row.get("投资评级") or ""),
                        "data_source": "akshare_research_report",
                    })
                return rows

            results = await asyncio.gather(*(fetch_one(code) for code in codes), return_exceptions=True)
            for result in results:
                if isinstance(result, list):
                    reports.extend(result)
        except Exception as e:
            logger.debug("研报抓取失败: %s", e)
        return reports

    async def _load_recent_analysis_candidates(self, statuses: List[SourceStatus]) -> List[Candidate]:
        try:
            cutoff = _utc_now() - timedelta(days=settings.MARKET_INTELLIGENCE_RECENT_ANALYSIS_DAYS)
            candidates: Dict[str, Candidate] = {}
            task_cursor = self.db.analysis_tasks.find(
                {"created_at": {"$gte": cutoff}},
                {"stock_code": 1, "stock_symbol": 1, "symbol": 1, "stock_name": 1, "status": 1, "updated_at": 1, "created_at": 1},
            ).sort("created_at", -1).limit(80)
            report_cursor = self.db.analysis_reports.find(
                {"created_at": {"$gte": cutoff}},
                {"stock_symbol": 1, "stock_code": 1, "stock_name": 1, "updated_at": 1, "created_at": 1},
            ).sort("created_at", -1).limit(80)
            rows = await task_cursor.to_list(length=80)
            rows.extend(await report_cursor.to_list(length=80))
            for row in rows:
                code = _normalize_code(row.get("stock_code") or row.get("stock_symbol") or row.get("symbol"))
                if not code:
                    continue
                score = 34.0
                if str(row.get("status") or "").lower() in {"processing", "running", "pending"}:
                    score += 8
                candidates[code] = Candidate(
                    code=code,
                    name=str(row.get("stock_name") or ""),
                    score=score,
                    source="最近个股分析",
                    reason=f"最近{settings.MARKET_INTELLIGENCE_RECENT_ANALYSIS_DAYS}天被用户分析过，持续跟踪新闻和舆情",
                    metadata={"analysis_status": row.get("status"), "created_at": row.get("created_at")},
                )
            values = list(candidates.values())
            statuses.append(SourceStatus("recent_analysis_stocks", bool(values), len(values), "读取最近分析/正在分析股票"))
            return values
        except Exception as e:
            statuses.append(SourceStatus("recent_analysis_stocks", False, 0, str(e)))
            return []

    def _merge_candidates(self, base: List[Candidate], extra: List[Candidate]) -> List[Candidate]:
        merged: Dict[str, Candidate] = {item.code: item for item in base if item.code}
        for item in extra:
            if not item.code:
                continue
            if item.code not in merged:
                merged[item.code] = item
            else:
                merged[item.code].score += min(12, item.score / 4)
                if item.source and item.source not in merged[item.code].source:
                    merged[item.code].source += f"+{item.source}"
                if item.reason and item.reason not in merged[item.code].reason:
                    merged[item.code].reason = f"{merged[item.code].reason}; {item.reason}".strip("; ")
        values = list(merged.values())
        values.sort(key=lambda item: item.score, reverse=True)
        return values

    async def _persist_rolling_sources(
        self,
        daily_service: Any,
        market_news: List[Dict[str, Any]],
        stock_news: List[Dict[str, Any]],
        announcements: List[Dict[str, Any]],
        reports: List[Dict[str, Any]],
        guba_posts: List[Dict[str, Any]],
    ) -> None:
        try:
            await daily_service._persist_news(market_news + stock_news + announcements + reports)
        except Exception as e:
            logger.debug("滚动新闻入stock_news失败: %s", e)
        try:
            await daily_service._persist_social(guba_posts)
        except Exception as e:
            logger.debug("滚动股吧评论入social_media失败: %s", e)

    async def _fetch_announcements(self, daily_service: Any, codes: List[str]) -> List[Dict[str, Any]]:
        announcements: List[Dict[str, Any]] = []
        if not codes:
            return announcements

        async def fetch_one(code: str) -> List[Dict[str, Any]]:
            try:
                return await daily_service._fetch_eastmoney_search(
                    f"{code} 公告",
                    4,
                    symbol=code,
                )
            except Exception as e:
                logger.debug("公告元数据抓取失败 %s: %s", code, e)
                return []

        results = await asyncio.gather(*(fetch_one(code) for code in codes), return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                for item in result:
                    text = f"{item.get('title', '')} {item.get('content', '')}"
                    if "公告" in text or "披露" in text or "提示性" in text:
                        item["data_source"] = item.get("data_source") or "eastmoney_announcement_search"
                        item["source"] = item.get("source") or "东方财富公告"
                        announcements.append(item)
        return announcements

    def _normalize_news_documents(self, items: Iterable[Dict[str, Any]], doc_type: str, window_start: datetime) -> List[Dict[str, Any]]:
        docs = []
        for item in items:
            published = _parse_dt(item.get("publish_time"))
            if published < window_start:
                continue
            title = str(item.get("title") or "").strip()
            content = str(item.get("content") or item.get("summary") or "").strip()
            if not title:
                continue
            text = f"{title} {content}"
            symbol = _normalize_code(item.get("symbol"))
            docs.append(self._document(
                document_type=doc_type,
                title=title,
                content=content,
                source=str(item.get("source") or "未知来源"),
                url=str(item.get("url") or ""),
                published_at=published,
                symbols=[symbol] if symbol else [],
                themes=self._match_themes(text),
                sentiment_score=_safe_float(item.get("sentiment_score"), _sentiment_score(text)),
                data_source=str(item.get("data_source") or "news"),
                metadata={k: _jsonable(v) for k, v in item.items() if k not in {"title", "content", "summary"}},
            ))
        return docs

    def _normalize_quant_signal_documents(self, candidates: Iterable[Candidate]) -> List[Dict[str, Any]]:
        docs = []
        local_now = now_tz()
        published = datetime(local_now.year, local_now.month, local_now.day)
        for candidate in candidates:
            if not candidate.code:
                continue
            text = f"{candidate.name} {candidate.reason} {candidate.source}"
            score = max(-1.0, min(1.0, (_safe_float(candidate.score) - 50) / 50))
            docs.append(self._document(
                document_type="quant_signal",
                title=f"{candidate.name or candidate.code} 量化策略信号",
                content=candidate.reason or "来自本地量化策略信号",
                source=candidate.source or "量化策略",
                url="",
                published_at=published,
                symbols=[candidate.code],
                themes=self._match_themes(text),
                sentiment_score=score,
                data_source="quant_signal_files",
                metadata={**candidate.metadata, "candidate_score": candidate.score},
            ))
        return docs

    def _normalize_social_documents(self, items: Iterable[Dict[str, Any]], window_start: datetime) -> List[Dict[str, Any]]:
        docs = []
        for item in items:
            published = _parse_dt(item.get("publish_time"))
            if published < window_start:
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            symbol = _normalize_code(item.get("symbol"))
            docs.append(self._document(
                document_type="social_comment",
                title=content[:80],
                content=content,
                source="东方财富股吧",
                url=str(item.get("url") or ""),
                published_at=published,
                symbols=[symbol] if symbol else [],
                themes=self._match_themes(content),
                sentiment_score=_safe_float(item.get("sentiment_score"), _sentiment_score(content)),
                data_source=str(item.get("data_source") or "eastmoney_guba"),
                metadata={k: _jsonable(v) for k, v in item.items() if k not in {"content"}},
            ))
        return docs

    def _normalize_research_documents(self, items: Iterable[Dict[str, Any]], window_start: datetime) -> List[Dict[str, Any]]:
        docs = []
        for item in items:
            published = _parse_dt(item.get("publish_time"))
            if published < window_start:
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            content = str(item.get("content") or "")
            text = f"{title} {content}"
            symbol = _normalize_code(item.get("symbol"))
            docs.append(self._document(
                document_type="research_report",
                title=title,
                content=content,
                source=str(item.get("source") or "东方财富研报"),
                url=str(item.get("url") or ""),
                published_at=published,
                symbols=[symbol] if symbol else [],
                themes=self._match_themes(text),
                sentiment_score=_safe_float(item.get("sentiment_score"), _sentiment_score(text)),
                data_source=str(item.get("data_source") or "akshare_research_report"),
                metadata={k: _jsonable(v) for k, v in item.items() if k not in {"title", "content"}},
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
        themes: List[str],
        sentiment_score: float,
        data_source: str,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        doc_key = hashlib.sha1(
            f"{url}|{title}|{published_at.isoformat()}|{source}".encode("utf-8")
        ).hexdigest()
        source_weight = max(SOURCE_WEIGHTS.get(source, SOURCE_WEIGHTS.get(data_source, 1.0)), 0.5)
        influence = min(100.0, 45 + len(content) / 25 + len(themes) * 6 + source_weight * 8)
        return {
            "doc_key": doc_key,
            "document_type": document_type,
            "title": title,
            "content": content,
            "summary": content[:240],
            "source": source,
            "data_source": data_source,
            "url": url,
            "published_at": published_at,
            "ingested_at": _utc_now(),
            "symbols": [s for s in symbols if s],
            "themes": themes,
            "sentiment": _sentiment_label(sentiment_score),
            "sentiment_score": sentiment_score,
            "source_weight": source_weight,
            "influence_score": round(influence, 2),
            "metadata": metadata,
        }

    async def _save_documents(self, documents: List[Dict[str, Any]]) -> int:
        saved = 0
        for doc in documents:
            result = await self.db.market_documents.replace_one(
                {"doc_key": doc["doc_key"]},
                doc,
                upsert=True,
            )
            if result.upserted_id or result.modified_count:
                saved += 1
        return saved

    async def _save_global_events(self, events: List[Dict[str, Any]]) -> int:
        saved = 0
        for event in events:
            result = await self.db.global_events.replace_one(
                {"event_id": event["event_id"]},
                event,
                upsert=True,
            )
            if result.upserted_id or result.modified_count:
                saved += 1
        return saved

    def _extract_global_events(self, documents: List[Dict[str, Any]], window_start: datetime) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        for doc in documents:
            if doc.get("published_at") < window_start:
                continue
            text = f"{doc.get('title', '')} {doc.get('content', '')}"
            if not self._looks_global_event(text):
                continue
            rule = self._geo_rule_for_text(text)
            if not rule:
                continue
            severity = self._event_severity(text, doc, rule)
            event_id = hashlib.sha1(
                f"{doc.get('doc_key')}|{rule['name']}".encode("utf-8")
            ).hexdigest()[:24]
            event_themes = sorted(set(rule.get("themes", []) + doc.get("themes", [])))
            event = {
                "event_id": event_id,
                "event_type": self._event_type(text),
                "title": doc.get("title"),
                "summary": doc.get("summary") or doc.get("content", "")[:240],
                "source": doc.get("source"),
                "url": doc.get("url"),
                "published_at": doc.get("published_at"),
                "ingested_at": _utc_now(),
                "lat": rule["lat"],
                "lon": rule["lon"],
                "country": rule["country"],
                "region": rule["region"],
                "location_name": rule["name"],
                "severity": severity,
                "confidence": 0.72 if rule.get("country") != "待定位" else 0.46,
                "affected_assets": rule.get("affected_assets", []),
                "transmission_channels": rule.get("transmission_channels", []),
                "mapped_themes": event_themes,
                "mapped_stocks": doc.get("symbols", []),
                "map_layers": self._event_layers_for_event(text, doc, rule),
                "document_key": doc.get("doc_key"),
            }
            events.append(event)
        events.sort(key=lambda item: (_safe_float(item.get("severity")), _parse_dt(item.get("published_at"))), reverse=True)
        return events

    def _looks_global_event(self, text: str) -> bool:
        return any(word in text for word in GLOBAL_KEYWORDS) or any(
            any(keyword in text for keyword in rule["keywords"]) for rule in EVENT_GEO_RULES
        )

    def _geo_rule_for_text(self, text: str) -> Optional[Dict[str, Any]]:
        for rule in EVENT_GEO_RULES:
            if any(keyword in text for keyword in rule["keywords"]):
                return rule
        return None

    def _event_type(self, text: str) -> str:
        if any(word in text for word in ["地震", "火灾", "台风", "洪水", "灾害"]):
            return "natural_disaster"
        if any(word in text for word in ["美联储", "央行", "CPI", "美元", "利率", "汇率"]):
            return "macro"
        if any(word in text for word in ["原油", "黄金", "铜", "煤炭", "大宗"]):
            return "commodity"
        if any(word in text for word in ["冲突", "战争", "制裁", "封锁", "袭击"]):
            return "geopolitical"
        return "global_news"

    def _event_severity(self, text: str, doc: Dict[str, Any], rule: Dict[str, Any]) -> float:
        score = 42 + _safe_float(rule.get("severity_bias")) + _safe_float(doc.get("influence_score")) * 0.18
        score += sum(5 for word in HIGH_SEVERITY_WORDS if word in text)
        score += abs(_safe_float(doc.get("sentiment_score"))) * 12
        return round(max(0.0, min(100.0, score)), 2)

    def _event_layers_for_event(self, text: str, doc: Dict[str, Any], rule: Dict[str, Any]) -> List[str]:
        event_type = self._event_type(text)
        mapped_themes = set(rule.get("themes", []) + doc.get("themes", []))
        layer_ids: List[str] = []
        for layer in WORLD_MONITOR_LAYERS:
            event_types = set(layer.get("event_types") or [])
            themes = set(layer.get("themes") or [])
            if layer["id"] == "a_share_mapping" and (mapped_themes or doc.get("symbols")):
                layer_ids.append(layer["id"])
                continue
            if event_type in event_types or mapped_themes.intersection(themes):
                layer_ids.append(layer["id"])
        return sorted(set(layer_ids))

    async def _recompute_signals(self, *, window_hours: int) -> Dict[str, Any]:
        dashboard = await self.build_dashboard_without_status(hours=window_hours)
        signal_date = now_tz().strftime("%Y-%m-%d")
        for theme in dashboard["theme_heatmap_nodes"]:
            await self.db.theme_signals.replace_one(
                {"signal_date": signal_date, "theme": theme["name"]},
                {"signal_date": signal_date, "updated_at": _utc_now(), "theme": theme["name"], **theme},
                upsert=True,
            )
        for stock in dashboard["stock_opportunities"]:
            await self.db.stock_signals.replace_one(
                {"signal_date": signal_date, "code": stock["code"]},
                {"signal_date": signal_date, "updated_at": _utc_now(), **stock},
                upsert=True,
            )
        return {"themes": dashboard["theme_heatmap_nodes"], "stocks": dashboard["stock_opportunities"]}

    async def build_dashboard_without_status(self, *, hours: int = 36) -> Dict[str, Any]:
        cutoff = _utc_now() - timedelta(hours=hours)
        documents = await self.db.market_documents.find(
            {"published_at": {"$gte": cutoff}}
        ).sort("published_at", -1).limit(300).to_list(length=300)
        events = await self.db.global_events.find(
            {"published_at": {"$gte": cutoff}}
        ).sort("published_at", -1).limit(100).to_list(length=100)
        events = [self._ensure_event_layers(event) for event in events]
        theme_nodes = self._build_theme_heatmap(documents, events)
        stock_opportunities = await self._build_stock_opportunities(documents, theme_nodes)
        return {"theme_heatmap_nodes": theme_nodes, "stock_opportunities": stock_opportunities}

    def _ensure_event_layers(self, event: Dict[str, Any]) -> Dict[str, Any]:
        if event.get("map_layers"):
            return event
        enriched = dict(event)
        event_type = str(enriched.get("event_type") or "")
        mapped_themes = set(enriched.get("mapped_themes") or [])
        layer_ids: List[str] = []
        for layer in WORLD_MONITOR_LAYERS:
            if layer["id"] == "a_share_mapping" and (mapped_themes or enriched.get("mapped_stocks")):
                layer_ids.append(layer["id"])
                continue
            if event_type in set(layer.get("event_types") or []) or mapped_themes.intersection(set(layer.get("themes") or [])):
                layer_ids.append(layer["id"])
        if self._matches_corridor(enriched):
            layer_ids.append("chokepoints")
        enriched["map_layers"] = sorted(set(layer_ids))
        return enriched

    def _build_map_layers(self, events: List[Dict[str, Any]], themes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        theme_scores = {theme.get("name"): _safe_float(theme.get("score")) for theme in themes}
        layers: List[Dict[str, Any]] = []
        for layer in WORLD_MONITOR_LAYERS:
            layer_id = layer["id"]
            layer_events = [event for event in events if layer_id in (event.get("map_layers") or [])]
            if layer_id == "chokepoints":
                layer_events = [
                    event for event in events
                    if event in layer_events or self._matches_corridor(event)
                ]
            score = max([_safe_float(event.get("severity")) for event in layer_events] or [0])
            related_theme_score = max(
                [theme_scores.get(theme, 0) for theme in layer.get("themes", [])] or [0]
            )
            layers.append({
                "id": layer_id,
                "label": layer["label"],
                "description": layer["description"],
                "color": layer["color"],
                "active": bool(layer_events),
                "event_count": len(layer_events),
                "max_severity": round(score, 2),
                "theme_score": round(related_theme_score, 2),
                "renderers": ["flat", "globe"],
            })
        return layers

    def _build_event_feed(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        feed = []
        for event in events[:80]:
            severity = _safe_float(event.get("severity"))
            feed.append({
                "event_id": event.get("event_id"),
                "title": event.get("title"),
                "summary": event.get("summary"),
                "source": event.get("source"),
                "published_at": event.get("published_at"),
                "severity": severity,
                "severity_label": "高" if severity >= 72 else "中" if severity >= 55 else "观察",
                "location_name": event.get("location_name") or event.get("region"),
                "layers": event.get("map_layers") or [],
                "mapped_themes": event.get("mapped_themes") or [],
                "affected_assets": event.get("affected_assets") or [],
            })
        return feed

    def _build_corridor_strip(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for corridor in STRATEGIC_CORRIDORS:
            related = [event for event in events if self._event_mentions_corridor(event, corridor)]
            max_severity = max([_safe_float(event.get("severity")) for event in related] or [0])
            score = min(100, _safe_float(corridor.get("base_risk")) * 0.35 + max_severity * 0.65 + len(related) * 3)
            status = "normal"
            if score >= 76:
                status = "critical"
            elif score >= 62:
                status = "high"
            elif score >= 48:
                status = "elevated"
            result.append({
                "id": corridor["id"],
                "name": corridor["name"],
                "region": corridor["region"],
                "lat": corridor["lat"],
                "lon": corridor["lon"],
                "status": status,
                "risk_score": round(score, 2),
                "event_count": len(related),
                "active_warnings": sum(
                    1 for event in related
                    if _safe_float(event.get("severity")) >= settings.MARKET_INTELLIGENCE_HIGH_SEVERITY_THRESHOLD
                ),
                "exposure": corridor["exposure"],
                "a_share_themes": corridor["a_share_themes"],
                "latest_event": related[0].get("title") if related else "",
            })
        result.sort(key=lambda item: (item["risk_score"], item["event_count"]), reverse=True)
        return result

    def _build_source_envelopes(self, documents: List[Dict[str, Any]], events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        envelopes = []
        now = _utc_now()
        for group in SOURCE_ENVELOPE_GROUPS:
            if group.get("event_group"):
                records = events
            else:
                doc_types = set(group.get("document_types") or [])
                records = [doc for doc in documents if doc.get("document_type") in doc_types]

            publish_times = [_parse_dt(record.get("published_at")) for record in records if record.get("published_at")]
            newest = max(publish_times) if publish_times else None
            oldest = min(publish_times) if publish_times else None
            age_minutes = int((now - newest).total_seconds() // 60) if newest else None
            max_age = int(group.get("max_age_minutes") or 30)
            if not records:
                state = "empty"
            elif age_minutes is not None and age_minutes > max_age:
                state = "stale"
            else:
                state = "fresh"
            envelopes.append({
                "id": group["id"],
                "label": group["label"],
                "schema_version": 1,
                "state": state,
                "record_count": len(records),
                "newest_item_at": newest,
                "oldest_item_at": oldest,
                "max_content_age_min": max_age,
                "age_minutes": age_minutes,
                "failed_datasets": [],
                "source_version": "market-intelligence-v1",
            })
        return envelopes

    def _matches_corridor(self, event: Dict[str, Any]) -> bool:
        return any(self._event_mentions_corridor(event, corridor) for corridor in STRATEGIC_CORRIDORS)

    def _event_mentions_corridor(self, event: Dict[str, Any], corridor: Dict[str, Any]) -> bool:
        text = " ".join(str(event.get(field) or "") for field in ["title", "summary", "location_name", "region", "country"])
        return any(keyword.lower() in text.lower() for keyword in corridor.get("keywords", []))

    def _build_theme_heatmap(self, documents: List[Dict[str, Any]], events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        nodes = []
        for theme, keywords in THEME_KEYWORDS.items():
            related_docs = [doc for doc in documents if theme in doc.get("themes", []) or self._matches(text=f"{doc.get('title','')} {doc.get('content','')}", keywords=keywords)]
            related_events = [event for event in events if theme in event.get("mapped_themes", [])]
            if not related_docs and not related_events:
                continue
            heat = len(related_docs) * 8 + len(related_events) * 12
            sentiment = sum(_safe_float(doc.get("sentiment_score")) for doc in related_docs)
            influence = sum(_safe_float(doc.get("influence_score")) for doc in related_docs)
            severity = max([_safe_float(e.get("severity")) for e in related_events] or [0])
            novelty = min(20, len({doc.get("source") for doc in related_docs}) * 4 + len(related_events) * 3)
            score = min(100.0, max(0.0, heat + sentiment * 6 + influence * 0.08 + novelty + severity * 0.12))
            nodes.append({
                "name": theme,
                "value": round(max(8.0, score), 2),
                "score": round(score, 2),
                "heat": round(heat, 2),
                "sentiment_score": round(sentiment / max(len(related_docs), 1), 3),
                "news_count": len(related_docs),
                "event_count": len(related_events),
                "risk_score": round(severity, 2),
                "trend": "up" if sentiment >= 0 else "watch",
                "keywords": keywords[:8],
                "headlines": [doc.get("title") for doc in related_docs[:4]],
            })
        nodes.sort(key=lambda item: item["score"], reverse=True)
        return nodes[:18]

    async def _build_stock_opportunities(self, documents: List[Dict[str, Any]], themes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        theme_score = {theme["name"]: _safe_float(theme.get("score")) for theme in themes}
        by_code: Dict[str, Dict[str, Any]] = {}
        for doc in documents:
            for code in doc.get("symbols", []):
                clean = _normalize_code(code)
                if not clean:
                    continue
                item = by_code.setdefault(clean, {
                    "code": clean,
                    "name": "",
                    "industry": "",
                    "theme": "",
                    "score": 0.0,
                    "news_count": 0,
                    "comment_count": 0,
                    "research_count": 0,
                    "announcement_count": 0,
                    "quant_count": 0,
                    "sentiment_score": 0.0,
                    "funds_score": 0.0,
                    "price_score": 0.0,
                    "risk_score": 0.0,
                    "headlines": [],
                    "documents": [],
                })
                doc_type = doc.get("document_type")
                item["news_count"] += 1 if doc_type in {"news", "stock_news"} else 0
                item["comment_count"] += 1 if doc_type == "social_comment" else 0
                item["research_count"] += 1 if doc_type == "research_report" else 0
                item["announcement_count"] += 1 if doc_type == "announcement" else 0
                item["quant_count"] += 1 if doc_type == "quant_signal" else 0
                item["sentiment_score"] += _safe_float(doc.get("sentiment_score"))
                item["score"] += 8 + _safe_float(doc.get("influence_score")) * 0.08
                for theme in doc.get("themes", []):
                    item["score"] += theme_score.get(theme, 0) * 0.06
                    if not item["theme"]:
                        item["theme"] = theme
                if len(item["headlines"]) < 4:
                    item["headlines"].append(doc.get("title"))
                if len(item["documents"]) < 8:
                    item["documents"].append(_jsonable(doc))

        if not by_code:
            return []

        basics = await self.db.stock_basic_info.find({"code": {"$in": list(by_code.keys())}}).to_list(length=len(by_code) * 2)
        for basic in basics:
            code = _normalize_code(basic.get("code"))
            if code in by_code:
                by_code[code]["name"] = basic.get("name") or by_code[code]["name"]
                by_code[code]["industry"] = basic.get("industry") or by_code[code]["industry"]

        quotes = await self.db.market_quotes.find({"code": {"$in": list(by_code.keys())}}).to_list(length=len(by_code))
        for quote in quotes:
            code = _normalize_code(quote.get("code"))
            if code in by_code:
                pct = _safe_float(quote.get("pct_chg"))
                amount = _safe_float(quote.get("amount"))
                by_code[code]["pct_chg"] = pct
                by_code[code]["amount"] = amount
                by_code[code]["price"] = _safe_float(quote.get("price") or quote.get("close"))
                by_code[code]["price_score"] = max(0, min(20, pct + 8))
                by_code[code]["funds_score"] = max(0, min(20, amount / 1_000_000_000))
                by_code[code]["score"] += by_code[code]["price_score"] + by_code[code]["funds_score"]

        result = []
        for item in by_code.values():
            total_docs = max(
                item["news_count"]
                + item["comment_count"]
                + item["research_count"]
                + item["announcement_count"]
                + item["quant_count"],
                1,
            )
            item["sentiment_score"] = round(item["sentiment_score"] / total_docs, 3)
            if item["sentiment_score"] < -0.3:
                item["risk_score"] += 12
            item["score"] = round(max(0, min(100, item["score"] - item["risk_score"])), 2)
            item["signal_strength"] = round(min(100, item["score"] + abs(item["sentiment_score"]) * 10), 2)
            if not item["name"]:
                item["name"] = item["code"]
            result.append(item)
        result.sort(key=lambda item: item["score"], reverse=True)
        return result[:40]

    def _build_industry_matrix(self, themes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        dimensions = ["主题热度", "舆情", "事件风险", "资金确认", "量价共振", "基本面"]
        rows = []
        for theme in themes[:10]:
            for idx, dim in enumerate(dimensions):
                base = _safe_float(theme.get("score"))
                value = base
                if dim == "舆情":
                    value = 50 + _safe_float(theme.get("sentiment_score")) * 50
                elif dim == "事件风险":
                    value = _safe_float(theme.get("risk_score"))
                elif dim in {"资金确认", "量价共振", "基本面"}:
                    value = max(15, base * (0.55 + idx * 0.05))
                rows.append({"theme": theme["name"], "dimension": dim, "value": round(min(100, max(0, value)), 2)})
        return rows

    def _build_event_impact_chains(self, events: List[Dict[str, Any]], themes: List[Dict[str, Any]], stocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        chains = []
        stock_by_theme: Dict[str, List[Dict[str, Any]]] = {}
        for stock in stocks:
            stock_by_theme.setdefault(stock.get("theme") or "未分类", []).append(stock)
        theme_names = {theme["name"] for theme in themes}
        for event in events:
            mapped_themes = [theme for theme in event.get("mapped_themes", []) if theme in theme_names]
            selected_stocks = []
            for theme in mapped_themes:
                selected_stocks.extend(stock_by_theme.get(theme, [])[:3])
            chains.append({
                "event_id": event.get("event_id"),
                "event_title": event.get("title"),
                "severity": event.get("severity"),
                "location_name": event.get("location_name"),
                "steps": [
                    {"label": "事件", "value": event.get("summary") or event.get("title")},
                    {"label": "资产/变量", "value": "、".join(event.get("affected_assets", [])[:4])},
                    {"label": "传导渠道", "value": "、".join(event.get("transmission_channels", [])[:4])},
                    {"label": "A股主题", "value": "、".join(mapped_themes[:5])},
                    {"label": "候选股票", "value": "、".join(f"{s.get('name')}({s.get('code')})" for s in selected_stocks[:5]) or "等待资金/量价确认"},
                ],
                "mapped_themes": mapped_themes,
                "mapped_stocks": selected_stocks[:8],
            })
        chains.sort(key=lambda item: _safe_float(item.get("severity")), reverse=True)
        return chains

    def _build_risk_warnings(self, events: List[Dict[str, Any]], source_statuses: List[Dict[str, Any]]) -> List[str]:
        warnings = []
        for event in events[:5]:
            if _safe_float(event.get("severity")) >= settings.MARKET_INTELLIGENCE_HIGH_SEVERITY_THRESHOLD:
                warnings.append(f"高严重度全球事件: {event.get('location_name')} - {event.get('title')}")
        stale = [s for s in source_statuses if not s.get("ok") and _safe_float(s.get("lag_minutes")) > 15]
        if stale:
            warnings.append(f"核心数据源超过15分钟未成功更新: {', '.join(s.get('name') for s in stale[:4])}")
        if not warnings:
            warnings.append("暂无高严重度事件，但仍需等待资金和量价确认")
        return warnings[:8]

    def _source_coverage(self, statuses: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not statuses:
            return {"score": 0, "ok_count": 0, "total": 0, "label": "暂无抓取记录"}
        ok_count = sum(1 for status in statuses if status.get("ok"))
        total = len(statuses)
        score = round(ok_count / max(total, 1) * 100, 1)
        return {
            "score": score,
            "ok_count": ok_count,
            "total": total,
            "label": "健康" if score >= 80 else "部分异常" if score >= 50 else "不足",
        }

    def _build_dashboard_summary(self, themes: List[Dict[str, Any]], stocks: List[Dict[str, Any]], events: List[Dict[str, Any]], risks: List[str]) -> str:
        lead_theme = themes[0]["name"] if themes else "暂无明确主线"
        lead_stock = f"{stocks[0].get('name')}({stocks[0].get('code')})" if stocks else "暂无"
        high_events = [e for e in events if _safe_float(e.get("severity")) >= settings.MARKET_INTELLIGENCE_HIGH_SEVERITY_THRESHOLD]
        return (
            f"当前主线聚焦 {lead_theme}，首个候选为 {lead_stock}。"
            f"近36小时识别全球事件 {len(events)} 个，其中高严重度 {len(high_events)} 个。"
            f"风险提示: {risks[0] if risks else '暂无'}。"
        )

    def _render_dashboard_markdown(self, summary: str, themes: List[Dict[str, Any]], stocks: List[Dict[str, Any]], chains: List[Dict[str, Any]], risks: List[str]) -> str:
        lines = [
            "# 市场情报报告",
            "",
            f"生成时间: {now_tz().strftime('%Y-%m-%d %H:%M')}",
            "",
            "## 核心结论",
            summary,
            "",
            "## 今日主线",
        ]
        for theme in themes[:6]:
            lines.append(f"- {theme['name']}: 综合分 {theme['score']}，新闻 {theme['news_count']} 条，事件 {theme['event_count']} 个")
        lines.extend(["", "## 全球事件传导"])
        for chain in chains[:4]:
            lines.append(f"- {chain.get('location_name')}: {chain.get('event_title')} -> {chain.get('steps', [{}])[3].get('value', '')}")
        lines.extend(["", "## 个股候选"])
        for stock in stocks[:8]:
            lines.append(f"- {stock.get('name')}({stock.get('code')}): {stock.get('theme')}，综合分 {stock.get('score')}，确认分 {stock.get('signal_strength')}")
        lines.extend(["", "## 风险反证"])
        for warning in risks:
            lines.append(f"- {warning}")
        lines.extend([
            "",
            "## 交易纪律",
            "- 只把信号当作观察清单，等待资金、量价和基本面证据共振。",
            "- 若舆情升温但资金流出或放量滞涨，按风险反噬处理。",
            "- 突发事件影响链需要持续验证是否已经 price in。",
        ])
        return "\n".join(lines)

    def _render_markdown_report(self, report_type: str, dashboard: Dict[str, Any]) -> str:
        title = self._report_type_name(report_type)
        return f"# {title}\n\n{dashboard.get('markdown_report') or dashboard.get('summary') or ''}"

    def _report_title(self, report_type: str, local_now: datetime) -> str:
        return f"{local_now.strftime('%Y-%m-%d %H:%M')} {self._report_type_name(report_type)}"

    def _report_type_name(self, report_type: str) -> str:
        return {
            "pre_market": "开盘前市场情报报告",
            "intraday": "盘中市场情报快报",
            "closing": "收盘复盘",
            "event_flash": "突发事件影响卡片",
            "research_digest": "晚间研报摘要",
        }.get(report_type, "市场情报报告")

    def _match_themes(self, text: str) -> List[str]:
        return [theme for theme, keywords in THEME_KEYWORDS.items() if self._matches(text=text, keywords=keywords)]

    def _matches(self, *, text: str, keywords: Iterable[str]) -> bool:
        return any(keyword and keyword.lower() in (text or "").lower() for keyword in keywords)


_market_intelligence_service: Optional[MarketIntelligenceService] = None


async def get_market_intelligence_service() -> MarketIntelligenceService:
    global _market_intelligence_service
    if _market_intelligence_service is None:
        _market_intelligence_service = MarketIntelligenceService()
        await _market_intelligence_service._ensure_indexes()
    return _market_intelligence_service
