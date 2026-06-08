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
from app.services.llm_task_router import get_llm_task_router
from app.services.public_intel_collector import get_public_intel_collector
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
    "SEC Latest Filings": 1.16,
    "Federal Reserve Press Releases": 1.22,
    "CFTC COT": 1.14,
    "CISA KEV JSON": 1.18,
    "NVD CVE API": 1.12,
    "CSIS": 1.18,
    "Atlantic Council": 1.12,
    "Brookings": 1.1,
    "Defense News": 1.12,
    "USNI News": 1.12,
    "Bellingcat": 1.1,
    "gCaptain": 1.1,
    "CNBC Markets": 1.08,
    "BBC World": 1.06,
    "Al Jazeera": 1.06,
    "GDELT DOC 2.1": 1.04,
    "public_feed": 1.04,
    "public_json": 1.08,
    "public_html": 0.92,
}

PUBLIC_THEME_KEYWORDS: Dict[str, List[str]] = {
    "AI算力": ["artificial intelligence", "generative ai", "data center", "datacenter", "gpu", "nvidia", "cloud", "compute", "hyperscaler", "large language model"],
    "半导体": ["semiconductor", "chip", "foundry", "wafer", "lithography", "tsmc", "eda", "memory", "advanced packaging"],
    "机器人": ["robot", "robotics", "humanoid", "automation", "autonomous", "drone", "uav"],
    "新能源": ["battery", "lithium", "solar", "renewable", "ev", "electric vehicle", "power grid", "storage"],
    "军工安全": ["defense", "military", "missile", "navy", "sanction", "security", "cyber", "vulnerability", "ransomware", "exploit"],
    "医药医疗": ["health", "disease", "outbreak", "vaccine", "pharma", "who", "cdc", "hospital"],
    "消费出海": ["trade", "tariff", "export", "shipping", "freight", "consumer", "e-commerce", "supply chain"],
    "资源通胀": ["oil", "crude", "lng", "gas", "copper", "gold", "commodity", "freight", "grain", "wheat", "food"],
    "金融地产": ["federal reserve", "fed", "treasury", "cpi", "inflation", "rate", "yield", "dollar", "liquidity", "bitcoin", "stablecoin", "bank"],
}

PUBLIC_INTEL_CATEGORY_PROFILES: Dict[str, Dict[str, Any]] = {
    "official_finance": {
        "label": "海外官方金融披露",
        "event_type": "macro",
        "lat": 38.9,
        "lon": -77.03,
        "region": "北美",
        "country": "美国",
        "themes": ["金融地产", "AI算力"],
        "affected_assets": ["美元", "美债", "全球风险偏好", "成长股估值"],
        "transmission_channels": ["流动性", "估值折现率", "外资风险偏好"],
        "severity_bias": 8,
    },
    "macro": {
        "label": "全球宏观政策",
        "event_type": "macro",
        "lat": 38.9,
        "lon": -77.03,
        "region": "全球宏观",
        "country": "美国/全球",
        "themes": ["金融地产", "资源通胀", "消费出海"],
        "affected_assets": ["美元", "美债", "黄金", "人民币汇率"],
        "transmission_channels": ["利率", "汇率", "通胀预期", "外需"],
        "severity_bias": 10,
    },
    "global_macro": {
        "label": "全球宏观新闻",
        "event_type": "macro",
        "lat": 38.9,
        "lon": -77.03,
        "region": "全球宏观",
        "country": "美国/全球",
        "themes": ["金融地产", "资源通胀", "消费出海"],
        "affected_assets": ["美元", "美债", "黄金", "人民币汇率"],
        "transmission_channels": ["利率", "汇率", "通胀预期", "外需"],
        "severity_bias": 8,
    },
    "markets_news": {
        "label": "海外市场新闻",
        "event_type": "macro",
        "lat": 40.71,
        "lon": -74.0,
        "region": "全球市场",
        "country": "美国/全球",
        "themes": ["金融地产", "资源通胀", "AI算力"],
        "affected_assets": ["美股", "美元", "商品", "风险偏好"],
        "transmission_channels": ["跨市场情绪", "资金风险偏好", "估值联动"],
        "severity_bias": 7,
    },
    "world_news": {
        "label": "全球新闻事件",
        "event_type": "geopolitical",
        "lat": 30.0,
        "lon": 20.0,
        "region": "全球",
        "country": "多区域",
        "themes": ["军工安全", "资源通胀", "消费出海"],
        "affected_assets": ["原油", "黄金", "航运", "出口链"],
        "transmission_channels": ["地缘风险", "贸易预期", "避险情绪"],
        "severity_bias": 11,
    },
    "global_news": {
        "label": "GDELT 全球事件",
        "event_type": "geopolitical",
        "lat": 30.0,
        "lon": 20.0,
        "region": "全球",
        "country": "多区域",
        "themes": ["军工安全", "资源通胀", "消费出海"],
        "affected_assets": ["原油", "黄金", "航运", "出口链"],
        "transmission_channels": ["地缘风险", "跨区域舆情扩散", "风险偏好"],
        "severity_bias": 13,
    },
    "think_tank": {
        "label": "智库战略风险",
        "event_type": "geopolitical",
        "lat": 38.9,
        "lon": -77.03,
        "region": "全球战略",
        "country": "美国/全球",
        "themes": ["军工安全", "半导体", "消费出海"],
        "affected_assets": ["贸易政策", "制裁链", "国防安全"],
        "transmission_channels": ["政策预期", "产业限制", "供应链重构"],
        "severity_bias": 12,
    },
    "defense": {
        "label": "军事活动与国防订单",
        "event_type": "geopolitical",
        "lat": 38.9,
        "lon": -77.03,
        "region": "全球防务",
        "country": "美国/全球",
        "themes": ["军工安全", "半导体", "AI算力"],
        "affected_assets": ["军工订单", "卫星链", "网络安全", "无人系统"],
        "transmission_channels": ["国防预算", "装备需求", "安全溢价"],
        "severity_bias": 15,
    },
    "osint": {
        "label": "OSINT 开源情报",
        "event_type": "geopolitical",
        "lat": 50.45,
        "lon": 30.52,
        "region": "全球冲突区",
        "country": "多区域",
        "themes": ["军工安全", "资源通胀"],
        "affected_assets": ["冲突风险", "能源", "黄金"],
        "transmission_channels": ["战况变化", "制裁预期", "避险交易"],
        "severity_bias": 14,
    },
    "maritime": {
        "label": "航运与关键通道",
        "event_type": "commodity",
        "lat": 1.29,
        "lon": 103.85,
        "region": "全球航运",
        "country": "新加坡/关键航道",
        "themes": ["资源通胀", "消费出海", "军工安全"],
        "affected_assets": ["集运", "油运", "运价", "出口交付"],
        "transmission_channels": ["航运价格", "保险成本", "交付周期"],
        "severity_bias": 14,
    },
    "tech": {
        "label": "科技供应链",
        "event_type": "tech_supply_chain",
        "lat": 37.39,
        "lon": -122.08,
        "region": "北美科技",
        "country": "美国/全球",
        "themes": ["AI算力", "半导体", "机器人"],
        "affected_assets": ["云资本开支", "GPU/ASIC", "软件生态"],
        "transmission_channels": ["产业景气", "订单预期", "国产替代"],
        "severity_bias": 7,
    },
    "research": {
        "label": "前沿技术研究",
        "event_type": "tech_supply_chain",
        "lat": 37.39,
        "lon": -122.08,
        "region": "全球科研",
        "country": "全球",
        "themes": ["AI算力", "半导体", "机器人"],
        "affected_assets": ["AI 模型", "算力需求", "芯片生态"],
        "transmission_channels": ["技术路线", "资本开支", "应用扩散"],
        "severity_bias": 6,
    },
    "startups": {
        "label": "创业与应用扩散",
        "event_type": "tech_supply_chain",
        "lat": 37.78,
        "lon": -122.42,
        "region": "北美科技",
        "country": "美国/全球",
        "themes": ["AI算力", "机器人", "消费出海"],
        "affected_assets": ["AI 应用", "SaaS", "算力需求"],
        "transmission_channels": ["应用渗透率", "云需求", "风险投资"],
        "severity_bias": 5,
    },
    "cyber": {
        "label": "网络威胁",
        "event_type": "cyber",
        "lat": 38.9,
        "lon": -77.03,
        "region": "全球网络空间",
        "country": "美国/全球",
        "themes": ["军工安全", "AI算力", "半导体"],
        "affected_assets": ["网络安全", "数据安全", "关键基础设施"],
        "transmission_channels": ["漏洞利用", "勒索攻击", "合规投入", "安全订单"],
        "severity_bias": 16,
    },
    "crypto": {
        "label": "加密与链上流动性",
        "event_type": "crypto_financial",
        "lat": 40.71,
        "lon": -74.0,
        "region": "全球金融",
        "country": "全球",
        "themes": ["金融地产", "AI算力"],
        "affected_assets": ["比特币", "稳定币", "美元流动性", "风险资产"],
        "transmission_channels": ["风险偏好", "美元流动性", "金融科技"],
        "severity_bias": 6,
    },
    "positioning": {
        "label": "期货持仓",
        "event_type": "commodity",
        "lat": 41.88,
        "lon": -87.63,
        "region": "全球商品",
        "country": "美国/全球",
        "themes": ["资源通胀", "金融地产"],
        "affected_assets": ["商品期货", "美元", "通胀预期"],
        "transmission_channels": ["投机持仓", "价格趋势", "套保需求"],
        "severity_bias": 7,
    },
    "health": {
        "label": "公共卫生",
        "event_type": "health",
        "lat": 46.2,
        "lon": 6.14,
        "region": "全球卫生",
        "country": "瑞士/全球",
        "themes": ["医药医疗", "消费出海"],
        "affected_assets": ["医药", "疫苗", "跨境出行", "消费"],
        "transmission_channels": ["公共卫生", "医疗需求", "出行限制"],
        "severity_bias": 11,
    },
    "food": {
        "label": "粮食与农业",
        "event_type": "food_security",
        "lat": 41.9,
        "lon": 12.5,
        "region": "全球农业",
        "country": "意大利/全球",
        "themes": ["资源通胀", "消费出海"],
        "affected_assets": ["粮食", "农产品", "食品价格"],
        "transmission_channels": ["农产品价格", "食品成本", "贸易流"],
        "severity_bias": 10,
    },
    "china_finance": {
        "label": "中国财经公共源",
        "event_type": "macro",
        "lat": 39.9,
        "lon": 116.4,
        "region": "中国",
        "country": "中国",
        "themes": list(THEME_KEYWORDS.keys()),
        "affected_assets": ["A股", "人民币", "政策预期"],
        "transmission_channels": ["政策", "资金风险偏好", "行业景气"],
        "severity_bias": 7,
    },
}

LOCATION_HINTS: List[Dict[str, Any]] = [
    {"keywords": ["China", "Chinese", "Beijing", "中国", "北京"], "lat": 39.9, "lon": 116.4, "region": "中国", "country": "中国", "name": "中国/北京"},
    {"keywords": ["United States", "U.S.", "US ", "America", "Washington", "美国"], "lat": 38.9, "lon": -77.03, "region": "北美", "country": "美国", "name": "美国/华盛顿"},
    {"keywords": ["Europe", "European", "EU ", "Brussels", "欧盟", "欧洲"], "lat": 50.85, "lon": 4.35, "region": "欧洲", "country": "欧盟", "name": "欧洲/布鲁塞尔"},
    {"keywords": ["Middle East", "Gulf", "Iran", "Israel", "中东", "伊朗", "以色列"], "lat": 31.77, "lon": 35.21, "region": "中东", "country": "中东", "name": "中东局势"},
    {"keywords": ["Russia", "Ukraine", "Black Sea", "俄罗斯", "乌克兰", "黑海"], "lat": 50.45, "lon": 30.52, "region": "欧洲", "country": "乌克兰/俄罗斯", "name": "俄乌/黑海"},
    {"keywords": ["Japan", "Tokyo", "日本", "东京"], "lat": 35.68, "lon": 139.76, "region": "亚洲", "country": "日本", "name": "日本/东京"},
    {"keywords": ["Korea", "Seoul", "韩国", "首尔"], "lat": 37.56, "lon": 126.97, "region": "亚洲", "country": "韩国", "name": "韩国/首尔"},
    {"keywords": ["Taiwan", "Taiwan Strait", "台湾", "台海"], "lat": 24.0, "lon": 121.0, "region": "亚太", "country": "中国台湾", "name": "台海/西太平洋"},
    {"keywords": ["Singapore", "Malacca", "Singapore Strait", "新加坡", "马六甲"], "lat": 1.29, "lon": 103.85, "region": "东南亚", "country": "新加坡/马六甲", "name": "马六甲/新加坡"},
    {"keywords": ["Red Sea", "Suez", "红海", "苏伊士"], "lat": 20.3, "lon": 38.5, "region": "中东/非洲", "country": "红海航道", "name": "红海/苏伊士"},
    {"keywords": ["Panama", "巴拿马"], "lat": 9.08, "lon": -79.68, "region": "拉美", "country": "巴拿马", "name": "巴拿马运河"},
]

THEME_INDUSTRY_HINTS: Dict[str, List[str]] = {
    "AI算力": ["通信", "光模块", "光器件", "光通信", "数据中心", "服务器", "云计算", "算力", "液冷", "PCB", "高速连接", "软件", "计算机", "互联网"],
    "半导体": ["半导体", "芯片", "集成电路", "晶圆", "封测", "半导体设备", "半导体材料", "存储", "光刻", "EDA", "功率器件"],
    "机器人": ["机器人", "自动化", "伺服", "减速器", "传感器", "机器视觉", "工业母机", "控制器", "智能制造"],
    "新能源": ["新能源", "电池", "锂电", "储能", "光伏", "风电", "充电", "电力设备", "电源设备", "逆变器", "电机", "汽车零部件", "宁德", "阳光电源"],
    "军工安全": ["军工", "航天", "航空", "卫星", "无人机", "雷达", "船舶", "兵器", "信息安全", "网络安全", "低空"],
    "医药医疗": ["医药", "医疗", "器械", "创新药", "CXO", "生物", "疫苗", "中药", "化学制药", "医疗服务"],
    "消费出海": ["家电", "消费", "食品", "饮料", "服装", "跨境", "电商", "旅游", "酒店", "出口", "轻工", "纺织", "品牌"],
    "资源通胀": ["有色", "黄金", "铜", "铝", "稀土", "煤炭", "石油", "油气", "化工", "钢铁", "农产品", "航运"],
    "金融地产": ["银行", "证券", "券商", "保险", "地产", "房地产", "多元金融", "信托", "并购", "资产管理"],
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
        "event_types": ["tech_supply_chain"],
        "themes": ["AI算力", "半导体", "机器人", "新能源"],
        "color": "#8b7cf6",
    },
    {
        "id": "cyber_threats",
        "label": "网络威胁",
        "description": "漏洞、勒索软件、关键基础设施攻击和安全合规投入",
        "event_types": ["cyber"],
        "themes": ["军工安全", "AI算力", "半导体"],
        "color": "#f45d96",
    },
    {
        "id": "crypto_fintech",
        "label": "金融科技/加密",
        "description": "稳定币、加密资产、链上流动性和风险偏好",
        "event_types": ["crypto_financial"],
        "themes": ["金融地产", "AI算力"],
        "color": "#d6b44c",
    },
    {
        "id": "health_food",
        "label": "公共卫生/粮食",
        "description": "公共卫生、疫情、粮食供应和农产品价格扰动",
        "event_types": ["health", "food_security"],
        "themes": ["医药医疗", "资源通胀", "消费出海"],
        "color": "#45c27a",
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
    {"id": "public_world_news", "label": "全球新闻/RSS", "document_types": ["news"], "public_categories": ["world_news", "global_news", "global_macro", "markets_news"], "max_age_minutes": 15},
    {"id": "policy_think_tank", "label": "政策/智库", "document_types": ["news"], "public_categories": ["official_finance", "macro", "think_tank", "defense", "osint"], "max_age_minutes": 60},
    {"id": "cyber_tech_intel", "label": "网络/科技情报", "document_types": ["news"], "public_categories": ["cyber", "tech", "research", "startups"], "max_age_minutes": 60},
    {"id": "supply_chain_assets", "label": "供应链/资产", "document_types": ["news"], "public_categories": ["maritime", "positioning", "crypto", "health", "food", "china_finance"], "max_age_minutes": 60},
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


def _sigmoid_score(value: float, *, midpoint: float = 0.0, scale: float = 1.0) -> float:
    scale = scale or 1.0
    try:
        if not math.isfinite(value) or not math.isfinite(midpoint) or not math.isfinite(scale):
            return 0.0
        return 100.0 / (1.0 + math.exp(-(value - midpoint) / scale))
    except OverflowError:
        return 0.0 if value < midpoint else 100.0


def _finite_float(value: Any, default: float = 0.0) -> float:
    number = _safe_float(value, default)
    try:
        if not math.isfinite(number):
            return default
    except TypeError:
        return default
    return number


def _optional_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if value is None:
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        try:
            raw = float(value)
            if raw > 10_000_000_000:
                raw = raw / 1000
            if raw > 10_000:
                return datetime.fromtimestamp(raw)
        except Exception:
            return None
    text = str(value).strip()
    if not text or text in {"-", "None", "null", "nan"}:
        return None
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
    match = re.search(r"(?:(\d{4})[年/-])?(\d{1,2})[月/-](\d{1,2})日?(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?", text)
    if match:
        year = int(match.group(1) or now_tz().year)
        hour = int(match.group(4) or 0)
        minute = int(match.group(5) or 0)
        second = int(match.group(6) or 0)
        try:
            return datetime(year, int(match.group(2)), int(match.group(3)), hour, minute, second)
        except Exception:
            return None
    return None


def _score_label(score: float) -> str:
    if score >= 80:
        return "强"
    if score >= 65:
        return "偏强"
    if score >= 45:
        return "中性"
    return "弱"


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
        await self.db.event_clusters.create_index([("cluster_id", 1)], unique=True, background=True)
        await self.db.event_clusters.create_index([("last_published_at", -1)], background=True)
        await self.db.company_exposures.create_index([("code", 1)], unique=True, background=True)
        await self.db.theme_signals.create_index(
            [("signal_date", -1), ("theme", 1)], background=True
        )
        await self.db.industry_signals.create_index(
            [("signal_date", -1), ("industry", 1)], background=True
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
        await self.db.event_impact_analyses.create_index([("event_id", 1)], unique=True, background=True)
        await self.db.prediction_evaluations.create_index([("signal_date", -1), ("code", 1)], background=True)
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
        if (
            job_id == "market_data_ingest_interval"
            and lookback_hours is None
            and not force_refresh
        ):
            previous = await self.db.crawler_runs.find_one(
                {"job_id": job_id, "status": "ready", "ended_at": {"$ne": None}},
                sort=[("ended_at", -1)],
            )
            if previous and previous.get("ended_at"):
                previous_end = _parse_dt(previous.get("ended_at"))
                cursor_start = previous_end - timedelta(minutes=10)
                window_start = min(window_start, cursor_start)
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
            public_items: List[Dict[str, Any]] = []
            public_statuses: List[Dict[str, Any]] = []
            if settings.MARKET_INTELLIGENCE_PUBLIC_SOURCES_ENABLED:
                public_items, public_statuses = await get_public_intel_collector().collect(window_start=window_start)

            for status in statuses:
                c = counter(status.name)
                c.fetched += status.count
                c.message = status.message
                if not status.ok:
                    c.failed += 1
            for status in public_statuses:
                c = counter(str(status.get("source") or "public_source"))
                c.fetched += int(status.get("fetched") or 0)
                c.failed += int(status.get("failed") or 0)
                c.latest_publish_time = status.get("latest_publish_time")
                c.message = str(status.get("message") or "")

            documents.extend(self._normalize_news_documents(market_news, "news", window_start))
            documents.extend(self._normalize_news_documents(public_items, "news", window_start))
            documents.extend(self._normalize_news_documents(stock_news, "stock_news", window_start))
            documents.extend(self._normalize_social_documents(guba_posts, window_start))
            documents.extend(self._normalize_research_documents(reports, window_start))
            documents.extend(self._normalize_news_documents(announcements, "announcement", window_start))
            documents.extend(self._normalize_quant_signal_documents(candidates))

            counter("market_documents").fetched = len(documents)
            counter("public_global_sources").fetched = len(public_items)
            counter("announcements").fetched = len(announcements)
            counter("research_reports").fetched = len(reports)
            counter("quant_signal_files").fetched = max(counter("quant_signal_files").fetched, len(candidates))
            global_events = self._extract_global_events(documents, window_start)
            counter("global_events").fetched = len(global_events)

            saved_documents, saved_by_source = await self._save_documents(documents)
            saved_events = await self._save_global_events(global_events)
            await self._persist_rolling_sources(daily, market_news, stock_news, announcements, reports, guba_posts)
            counter("market_documents").saved = saved_documents
            for status in public_statuses:
                source_name = str(status.get("source") or "").replace("public:", "", 1)
                counter(str(status.get("source") or "public_source")).saved = saved_by_source.get(source_name, 0)
            public_source_names = {str(item.get("source") or "") for item in public_items}
            counter("public_global_sources").saved = sum(saved_by_source.get(name, 0) for name in public_source_names)
            counter("global_events").saved = saved_events

            signals = await self._recompute_signals(window_hours=36)
            clusters = await self._recompute_event_clusters(window_hours=36)
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
                "cluster_count": len(clusters),
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
        doc_limit = 1200 if hours >= 120 else 500
        event_limit = 300 if hours >= 120 else 140
        documents = await self.db.market_documents.find(
            {"published_at": {"$gte": cutoff}}
        ).sort("published_at", -1).limit(doc_limit).to_list(length=doc_limit)
        events = await self.db.global_events.find(
            {"published_at": {"$gte": cutoff}}
        ).sort("published_at", -1).limit(event_limit).to_list(length=event_limit)
        events = [self._ensure_event_layers(event) for event in events]
        latest_report = await self.db.market_intelligence_reports.find_one(sort=[("generated_at", -1)])
        latest_run = await self.db.crawler_runs.find_one(sort=[("ended_at", -1)])
        crawler_statuses = await self.get_source_status()

        theme_nodes = self._build_theme_heatmap(documents, events)
        stock_opportunities = await self._build_stock_opportunities(documents, theme_nodes, events)
        industry_matrix = self._build_industry_matrix(theme_nodes)
        event_chains = self._build_event_impact_chains(events, theme_nodes, stock_opportunities)
        event_clusters = self._build_event_clusters(documents, events)
        risk_warnings = self._build_risk_warnings(events, crawler_statuses)
        map_layers = self._build_map_layers(events, theme_nodes)
        event_feed = self._build_event_feed(events)
        corridor_strip = self._build_corridor_strip(events)
        source_envelopes = self._build_source_envelopes(documents, events)
        high_event = any(_safe_float(event.get("severity")) >= settings.MARKET_INTELLIGENCE_HIGH_SEVERITY_THRESHOLD for event in events)
        source_coverage = self._source_coverage(crawler_statuses)

        summary = self._build_dashboard_summary(theme_nodes, stock_opportunities, events, risk_warnings)
        markdown_report = self._render_dashboard_markdown(summary, theme_nodes, stock_opportunities, event_chains, risk_warnings, source_envelopes)

        return _jsonable({
            "status": "ready" if documents or events else "partial",
            "summary": summary,
            "last_ingested_at": latest_run.get("ended_at") if latest_run else None,
            "last_report_generated_at": latest_report.get("generated_at") if latest_report else None,
            "source_coverage": source_coverage,
            "has_high_severity_event": high_event,
            "global_events": events[:80],
            "event_clusters": event_clusters[:30],
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

    async def get_documents(
        self,
        *,
        hours: int = 36,
        code: Optional[str] = None,
        cluster_id: Optional[str] = None,
        source: Optional[str] = None,
        document_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        await self._ensure_indexes()
        query: Dict[str, Any] = {"published_at": {"$gte": _utc_now() - timedelta(hours=hours)}}
        clean = _normalize_code(code) if code else None
        if clean:
            query["symbols"] = clean
        if source:
            query["source"] = source
        if document_type:
            query["document_type"] = document_type
        docs = await self.db.market_documents.find(query).sort("published_at", -1).limit(limit * 2).to_list(length=limit * 2)
        if cluster_id:
            clusters = self._build_event_clusters(docs, [])
            keys = set()
            for cluster in clusters:
                if cluster.get("cluster_id") == cluster_id:
                    keys.update(cluster.get("document_keys") or [])
            docs = [doc for doc in docs if doc.get("doc_key") in keys]
        return _jsonable(docs[:limit])

    async def get_event_clusters(self, *, hours: int = 36, limit: int = 50) -> List[Dict[str, Any]]:
        await self._ensure_indexes()
        cutoff = _utc_now() - timedelta(hours=hours)
        persisted = await self.db.event_clusters.find(
            {"last_published_at": {"$gte": cutoff}}
        ).sort("last_published_at", -1).limit(limit).to_list(length=limit)
        if persisted and all("linked_event_id" in cluster for cluster in persisted):
            return _jsonable(persisted)
        docs = await self.db.market_documents.find({"published_at": {"$gte": cutoff}}).sort("published_at", -1).limit(400).to_list(length=400)
        events = await self.db.global_events.find({"published_at": {"$gte": cutoff}}).sort("published_at", -1).limit(160).to_list(length=160)
        return _jsonable(self._build_event_clusters(docs, events)[:limit])

    async def get_stock_detail(self, code: str, *, hours: int = 72) -> Optional[Dict[str, Any]]:
        await self._ensure_indexes()
        clean = _normalize_code(code)
        if not clean:
            return None
        signal = await self.get_stock_signal(clean) or {"code": clean}
        docs = await self.get_documents(hours=hours, code=clean, limit=160)
        public_context = await self._stock_public_context(signal, hours=hours, limit=80)
        docs = self._dedupe_documents([*docs, *public_context])
        comments = await self.get_stock_comments(clean, hours=hours, limit=120)
        exposure = await self._get_company_exposure(clean, signal, docs)
        clusters = self._build_event_clusters(docs, [])
        signal["documents"] = docs[:80]
        signal["public_intel_context"] = public_context[:40]
        signal["event_clusters"] = clusters[:12]
        signal["comments"] = comments.get("comments", [])
        signal["sentiment_summary"] = comments.get("sentiment_summary", {})
        signal["company_exposure"] = exposure
        signal["methodology"] = self._stock_methodology()
        return _jsonable(signal)

    async def get_stock_comments(self, code: str, *, hours: int = 72, limit: int = 200) -> Dict[str, Any]:
        await self._ensure_indexes()
        clean = _normalize_code(code)
        if not clean:
            return {"comments": [], "sentiment_summary": {}}
        cutoff = _utc_now() - timedelta(hours=hours)
        docs = await self.db.market_documents.find(
            {"symbols": clean, "document_type": "social_comment", "published_at": {"$gte": cutoff}}
        ).sort("published_at", -1).limit(limit).to_list(length=limit)
        if not docs:
            docs = await self.db.social_media_messages.find(
                {"symbol": clean, "publish_time": {"$gte": cutoff}}
            ).sort("publish_time", -1).limit(limit).to_list(length=limit)
        comments = [_jsonable(doc) for doc in docs]
        scores = [_safe_float(doc.get("sentiment_score")) for doc in docs]
        pos = sum(1 for s in scores if s >= 0.25)
        neg = sum(1 for s in scores if s <= -0.25)
        neu = max(0, len(scores) - pos - neg)
        avg = sum(scores) / max(len(scores), 1)
        dispersion = (sum((s - avg) ** 2 for s in scores) / max(len(scores), 1)) ** 0.5 if scores else 0
        return _jsonable({
            "comments": comments,
            "sentiment_summary": {
                "count": len(comments),
                "positive": pos,
                "neutral": neu,
                "negative": neg,
                "avg_sentiment": round(avg, 3),
                "disagreement": round(dispersion, 3),
                "formula": "avg_sentiment=mean(sentiment_score); disagreement=stddev(sentiment_score)",
            },
        })

    async def _stock_public_context(self, signal: Dict[str, Any], *, hours: int, limit: int) -> List[Dict[str, Any]]:
        themes = list(dict.fromkeys(
            [theme for theme in (signal.get("matched_themes") or []) if theme]
            + ([signal.get("theme")] if signal.get("theme") else [])
        ))
        if not themes:
            return []
        cutoff = _utc_now() - timedelta(hours=hours)
        docs = await self.db.market_documents.find({
            "published_at": {"$gte": cutoff},
            "data_source": {"$regex": "^public_"},
            "themes": {"$in": themes},
        }).sort([("influence_score", -1), ("published_at", -1)]).limit(limit).to_list(length=limit)
        return _jsonable(docs)

    def _dedupe_documents(self, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        result = []
        for doc in docs:
            key = doc.get("doc_key") or doc.get("url") or doc.get("title")
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(doc)
        return result

    async def get_methodology(self) -> Dict[str, Any]:
        router = get_llm_task_router()
        return {
            "llm_policy": router.public_policy(),
            "stock_prediction_formula": self._stock_methodology(),
            "market_temperature_formula": {
                "formula": "25%市场广度 + 20%成交/换手 + 20%主题热度 + 15%新闻舆情 + 15%资金确认 - 15%全球风险",
                "normalization_method": "各项先映射到0-100，再按权重加权；风险项为扣分项",
            },
            "global_risk_formula": {
                "formula": "50%国家/区域风险 + 30%地理事件汇聚 + 20%基础设施/供应链风险 + 突发新闻加成",
                "normalization_method": "事件严重度、来源影响力、关键词强度和地理通道暴露综合",
            },
            "theme_formula": {
                "formula": "sigmoid(0.32*热度 + 0.18*情绪 + 0.18*来源影响力 + 0.14*新颖度 + 0.18*事件严重度)",
                "normalization_method": "sigmoid标准化，避免原始数量导致全100",
            },
        }

    async def analyze_event_impact(self, event_id: str, *, force: bool = False) -> Dict[str, Any]:
        await self._ensure_indexes()
        existing = await self.db.event_impact_analyses.find_one({"event_id": event_id})
        event = await self.get_global_event(event_id)
        if not event:
            raise ValueError("global event not found")
        if existing and not force:
            if existing.get("event_title") and existing.get("event_title") != event.get("title"):
                await self.db.event_impact_analyses.delete_one({"event_id": event_id})
            elif existing.get("status") in {"ready", "partial"}:
                return _jsonable(existing)
            elif existing.get("status") == "running":
                updated_at = _parse_dt(existing.get("updated_at"))
                if (_utc_now() - updated_at).total_seconds() < 20 * 60:
                    return _jsonable(existing)
        await self.db.event_impact_analyses.update_one(
            {"event_id": event_id},
            {"$set": {
                "event_id": event_id,
                "status": "running",
                "updated_at": _utc_now(),
                "event_title": event.get("title"),
            }},
            upsert=True,
        )
        docs = await self._event_evidence_docs(event, limit=60)
        prompt = self._event_analysis_prompt(event, docs)
        llm_result = await get_llm_task_router().chat_jsonish(
            task_type="event_impact",
            messages=[
                {"role": "system", "content": "你是生产级投行策略分析师。输出中文，结构清晰，必须给出事件到A股的传导链、受益受损行业、候选股票、证据和失效条件。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.15,
        )
        fallback = self._fallback_event_analysis(event, docs)
        analysis = {
            "event_id": event_id,
            "event_title": event.get("title"),
            "status": "ready" if llm_result.get("status") in {"ready", "skipped"} else "partial",
            "updated_at": _utc_now(),
            "model": llm_result.get("model"),
            "provider": llm_result.get("provider"),
            "analysis_markdown": llm_result.get("content") or fallback,
            "fallback_used": not bool(llm_result.get("content")),
            "usage": llm_result.get("usage") or {},
            "error": llm_result.get("error"),
            "event": event,
            "evidence": [_jsonable(doc) for doc in docs[:20]],
        }
        await self.db.event_impact_analyses.replace_one({"event_id": event_id}, analysis, upsert=True)
        return _jsonable(analysis)

    async def get_event_analysis(self, event_id: str) -> Optional[Dict[str, Any]]:
        await self._ensure_indexes()
        doc = await self.db.event_impact_analyses.find_one({"event_id": event_id})
        if doc:
            event = await self.get_global_event(event_id)
            if event and doc.get("event_title") and doc.get("event_title") != event.get("title"):
                await self.db.event_impact_analyses.delete_one({"event_id": event_id})
                return None
        return _jsonable(doc) if doc else None

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

    async def _recompute_event_clusters(self, *, window_hours: int) -> List[Dict[str, Any]]:
        cutoff = _utc_now() - timedelta(hours=window_hours)
        docs = await self.db.market_documents.find(
            {"published_at": {"$gte": cutoff}}
        ).sort("published_at", -1).limit(600).to_list(length=600)
        events = await self.db.global_events.find(
            {"published_at": {"$gte": cutoff}}
        ).sort("published_at", -1).limit(160).to_list(length=160)
        clusters = self._build_event_clusters(docs, events)
        for cluster in clusters:
            await self.db.event_clusters.replace_one(
                {"cluster_id": cluster["cluster_id"]},
                {**cluster, "updated_at": _utc_now()},
                upsert=True,
            )
        return clusters

    def _cluster_key_for_doc(self, doc: Dict[str, Any]) -> str:
        text = f"{doc.get('title', '')} {doc.get('content', '')}"
        matched_themes = doc.get("themes") or self._match_themes(text)
        symbols = doc.get("symbols") or []
        important_words = []
        for word in sorted(set(re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,}", text))):
            if word in HIGH_SEVERITY_WORDS or any(word in keywords for keywords in THEME_KEYWORDS.values()):
                important_words.append(word)
        if symbols:
            basis = f"stock:{symbols[0]}:{','.join(matched_themes[:2])}"
        elif matched_themes:
            basis = f"theme:{matched_themes[0]}:{','.join(important_words[:3])}"
        else:
            normalized = re.sub(r"\s+", "", str(doc.get("title") or ""))[:28]
            basis = f"title:{normalized}"
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:18]

    def _event_cluster_tokens(self, value: str) -> set[str]:
        stop_words = {
            "公司", "今日", "目前", "已经", "开始", "影响", "全球", "市场", "投资", "报告",
            "新闻", "评论", "表示", "认为", "可以", "还是", "没有", "风险", "数据",
            "public", "html", "link", "metadata", "http", "https", "www",
        }
        tokens = set()
        for token in re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]{2,}", value or ""):
            normalized = token.lower()
            if normalized in stop_words:
                continue
            tokens.add(normalized)
        return tokens

    def _score_cluster_event_link(self, cluster: Dict[str, Any], event: Dict[str, Any]) -> float:
        cluster_themes = set(cluster.get("themes") or [])
        event_themes = set(event.get("mapped_themes") or [])
        cluster_symbols = set(cluster.get("symbols") or [])
        event_symbols = set(event.get("mapped_stocks") or [])
        cluster_doc_types = set(cluster.get("document_types") or [])
        cluster_text = f"{cluster.get('title', '')} {cluster.get('summary', '')}"
        event_text = (
            f"{event.get('title', '')} {event.get('summary', '')} "
            f"{event.get('location_name', '')} {event.get('region', '')} {event.get('country', '')}"
        )
        cluster_tokens = self._event_cluster_tokens(cluster_text)
        event_tokens = self._event_cluster_tokens(event_text)

        theme_overlap = cluster_themes & event_themes
        symbol_overlap = cluster_symbols & event_symbols
        token_overlap = cluster_tokens & event_tokens
        score = 0.0
        if theme_overlap:
            score += 30.0 * len(theme_overlap) / max(len(cluster_themes | event_themes), 1)
        if symbol_overlap:
            score += 34.0 * len(symbol_overlap)
        if token_overlap:
            score += min(34.0, 5.0 * len(token_overlap))

        cluster_title = str(cluster.get("title") or "")
        event_title = str(event.get("title") or "")
        has_title_match = bool(cluster_title and event_title and (cluster_title in event_title or event_title in cluster_title))
        has_symbol_match = bool(symbol_overlap)
        has_token_match = len(token_overlap) >= 2
        is_comment_only = bool(cluster_doc_types) and cluster_doc_types <= {"social_comment"}
        if is_comment_only and not has_title_match and not has_token_match:
            return 0.0
        if not (has_title_match or has_token_match):
            return 0.0
        if has_title_match:
            score += 36.0

        cluster_time = _parse_dt(cluster.get("last_published_at"))
        event_time = _parse_dt(event.get("published_at"))
        gap_hours = abs((cluster_time - event_time).total_seconds()) / 3600
        score += max(0.0, 18.0 - gap_hours * 1.2)
        score += min(12.0, _safe_float(event.get("severity")) / 8.0)
        return round(score, 3)

    def _linked_event_for_cluster(self, cluster: Dict[str, Any], events: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], float]:
        if not events:
            return None, 0.0
        event_by_id = {event.get("event_id"): event for event in events if event.get("event_id")}
        direct_ids = [event_id for event_id in cluster.get("direct_event_ids", set()) if event_id in event_by_id]
        if direct_ids:
            direct = max(direct_ids, key=lambda event_id: _safe_float(event_by_id[event_id].get("severity")))
            return event_by_id[direct], 999.0

        best_event: Optional[Dict[str, Any]] = None
        best_score = 0.0
        for event in events:
            score = self._score_cluster_event_link(cluster, event)
            if score > best_score:
                best_event = event
                best_score = score
        if best_event and best_score >= 38.0:
            return best_event, best_score
        return None, best_score

    def _build_event_clusters(self, documents: List[Dict[str, Any]], events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}
        for doc in documents:
            title = str(doc.get("title") or "").strip()
            if not title:
                continue
            key = self._cluster_key_for_doc(doc)
            cluster = grouped.setdefault(key, {
                "cluster_id": key,
                "title": title,
                "summary": doc.get("summary") or doc.get("content", "")[:180],
                "document_keys": [],
                "documents": [],
                "sources": set(),
                "document_types": set(),
                "themes": set(),
                "symbols": set(),
                "first_published_at": _parse_dt(doc.get("published_at")),
                "last_published_at": _parse_dt(doc.get("published_at")),
                "sentiment_total": 0.0,
                "influence_total": 0.0,
                "event_count": 0,
                "event_ids": set(),
                "direct_event_ids": set(),
            })
            published = _parse_dt(doc.get("published_at"))
            cluster["document_keys"].append(doc.get("doc_key"))
            if len(cluster["documents"]) < 8:
                cluster["documents"].append(_jsonable(doc))
            cluster["sources"].add(str(doc.get("source") or doc.get("data_source") or "未知"))
            cluster["document_types"].add(str(doc.get("document_type") or "unknown"))
            cluster["themes"].update(doc.get("themes") or [])
            cluster["symbols"].update(doc.get("symbols") or [])
            cluster["first_published_at"] = min(cluster["first_published_at"], published)
            cluster["last_published_at"] = max(cluster["last_published_at"], published)
            cluster["sentiment_total"] += _safe_float(doc.get("sentiment_score"))
            cluster["influence_total"] += _safe_float(doc.get("influence_score"))

        for event in events:
            text = f"{event.get('title', '')} {event.get('summary', '')}"
            pseudo_doc = {
                "title": event.get("title"),
                "content": event.get("summary"),
                "themes": event.get("mapped_themes") or [],
                "symbols": event.get("mapped_stocks") or [],
            }
            key = f"event:{event.get('event_id') or hashlib.sha1(text.encode('utf-8')).hexdigest()[:18]}"
            cluster = grouped.setdefault(key, {
                "cluster_id": key,
                "title": event.get("title") or event.get("location_name") or "全球事件",
                "summary": event.get("summary") or text[:180],
                "document_keys": [],
                "documents": [],
                "sources": set(),
                "document_types": set(),
                "themes": set(),
                "symbols": set(),
                "first_published_at": _parse_dt(event.get("published_at")),
                "last_published_at": _parse_dt(event.get("published_at")),
                "sentiment_total": 0.0,
                "influence_total": 0.0,
                "event_count": 0,
                "event_ids": set(),
                "direct_event_ids": set(),
            })
            published = _parse_dt(event.get("published_at"))
            cluster["event_count"] += 1
            if event.get("event_id"):
                cluster["event_ids"].add(event.get("event_id"))
                if not cluster["document_keys"]:
                    cluster["direct_event_ids"].add(event.get("event_id"))
            cluster["sources"].add(str(event.get("source") or "全球事件"))
            cluster["themes"].update(event.get("mapped_themes") or [])
            cluster["symbols"].update(event.get("mapped_stocks") or [])
            cluster["first_published_at"] = min(cluster["first_published_at"], published)
            cluster["last_published_at"] = max(cluster["last_published_at"], published)
            cluster["influence_total"] += _safe_float(event.get("severity"))

        result: List[Dict[str, Any]] = []
        for cluster in grouped.values():
            doc_count = len(cluster["document_keys"])
            total_items = doc_count + cluster["event_count"]
            if total_items <= 0:
                continue
            avg_sentiment = cluster["sentiment_total"] / max(doc_count, 1)
            influence = cluster["influence_total"] / max(total_items, 1)
            heat_score = _sigmoid_score(total_items, midpoint=3, scale=2.2)
            impact_score = round(heat_score * 0.45 + min(100, influence) * 0.35 + (50 + avg_sentiment * 50) * 0.20, 2)
            linked_event, link_score = self._linked_event_for_cluster(cluster, events)
            result.append({
                "cluster_id": cluster["cluster_id"],
                "title": cluster["title"],
                "summary": cluster["summary"],
                "document_keys": [key for key in cluster["document_keys"] if key],
                "documents": cluster["documents"],
                "document_count": doc_count,
                "event_count": cluster["event_count"],
                "event_ids": sorted(cluster["event_ids"]),
                "linked_event_id": linked_event.get("event_id") if linked_event else None,
                "linked_event_title": linked_event.get("title") if linked_event else None,
                "linked_event_location": (linked_event.get("location_name") or linked_event.get("region")) if linked_event else None,
                "linked_event_severity": _safe_float(linked_event.get("severity")) if linked_event else None,
                "linked_event_score": link_score,
                "source_count": len(cluster["sources"]),
                "sources": sorted(cluster["sources"]),
                "document_types": sorted(cluster["document_types"]),
                "themes": sorted(cluster["themes"]),
                "symbols": sorted(cluster["symbols"]),
                "first_published_at": cluster["first_published_at"],
                "last_published_at": cluster["last_published_at"],
                "avg_sentiment": round(avg_sentiment, 3),
                "impact_score": impact_score,
                "score_breakdown": {
                    "formula": "45%事件/新闻热度 + 35%来源影响力/事件严重度 + 20%情绪方向",
                    "input_values": {
                        "total_items": total_items,
                        "avg_influence_or_severity": round(influence, 2),
                        "avg_sentiment": round(avg_sentiment, 3),
                    },
                    "normalization_method": "热度使用sigmoid标准化，影响力和情绪映射到0-100后加权",
                },
            })
        result.sort(key=lambda item: (item["impact_score"], _parse_dt(item["last_published_at"])), reverse=True)
        return result

    async def _get_company_exposure(self, code: str, signal: Dict[str, Any], docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        existing = await self.db.company_exposures.find_one({"code": code})
        if existing:
            return _jsonable(existing)
        text = " ".join([str(signal.get("industry") or ""), str(signal.get("theme") or "")] + [str(doc.get("title") or "") for doc in docs[:20]])
        themes = set(signal.get("theme") for _ in [0] if signal.get("theme"))
        for doc in docs:
            themes.update(doc.get("themes") or [])
        export_markets: List[str] = []
        upstream: List[str] = []
        downstream: List[str] = []
        chokepoints: List[str] = []
        if any(theme in themes for theme in ["消费出海", "新能源", "半导体", "AI算力"]):
            export_markets.extend(["美国", "欧洲", "东南亚"])
            chokepoints.extend(["马六甲海峡", "红海/苏伊士", "巴拿马运河"])
        if "资源通胀" in themes or any(word in text for word in ["油", "铜", "铝", "煤", "锂"]):
            upstream.extend(["能源", "有色金属", "化工原料"])
            chokepoints.append("霍尔木兹海峡")
        if "AI算力" in themes or "半导体" in themes:
            upstream.extend(["GPU/ASIC", "光模块", "PCB", "设备材料"])
            downstream.extend(["云厂商", "服务器", "数据中心"])
        if "机器人" in themes:
            upstream.extend(["减速器", "伺服系统", "传感器"])
            downstream.extend(["制造业自动化", "人形机器人整机"])
        exposure = {
            "code": code,
            "updated_at": _utc_now(),
            "export_markets": sorted(set(export_markets)) or ["待从年报/公告补全"],
            "upstream": sorted(set(upstream)) or ["待从研报/公告补全"],
            "downstream": sorted(set(downstream)) or ["待从研报/公告补全"],
            "critical_chokepoints": sorted(set(chokepoints)) or ["暂无明确通道暴露"],
            "confidence": 0.46 if not docs else 0.62,
            "method": "基于主题、行业、新闻/研报关键词的第一版映射；后续可用年报主营地区和客户数据校准",
        }
        await self.db.company_exposures.replace_one({"code": code}, exposure, upsert=True)
        return _jsonable(exposure)

    def _stock_methodology(self) -> Dict[str, Any]:
        return {
            "formula": "22%中长线基本面/产业位势 + 18%主题/事件暴露 + 14%新闻/研报/公告证据 + 10%民众评论 + 15%资金确认 + 11%量价结构 + 10%供应链/出口暴露 - 风险反噬 - price-in惩罚",
            "normalization_method": "候选池先做全市场扫描，再叠加事件推导范围；数量类因子使用sigmoid，估值/市值/换手映射为中长线位势，情绪从[-1,1]映射到[0,100]，禁止简单min(100, raw)打满分",
            "prediction_horizon": "中长线1-3个月；事件催化跟踪1-3个交易日",
            "not_buy_rule": "已大涨或涨停股票只有在新增催化、资金确认且price-in惩罚较低时保留为候选；缺少直接新闻不再给0分，但会降低证据分和置信度",
        }

    async def _event_evidence_docs(self, event: Dict[str, Any], *, limit: int = 60) -> List[Dict[str, Any]]:
        exact_key = event.get("document_key")
        mapped_symbols = set(event.get("mapped_stocks") or [])
        mapped_themes = event.get("mapped_themes") or []
        query_parts: List[Dict[str, Any]] = []
        if exact_key:
            query_parts.append({"doc_key": exact_key})
        if mapped_symbols:
            query_parts.append({"symbols": {"$in": sorted(mapped_symbols)}})
        if mapped_themes:
            query_parts.append({"themes": {"$in": mapped_themes}})
        if not query_parts:
            return []

        candidates = await self.db.market_documents.find({"$or": query_parts}).sort("published_at", -1).limit(220).to_list(length=220)
        event_text = (
            f"{event.get('title', '')} {event.get('summary', '')} {event.get('location_name', '')} "
            f"{event.get('country', '')} {event.get('region', '')}"
        )
        event_tokens = self._event_cluster_tokens(event_text)
        event_title = str(event.get("title") or "")
        scored: List[Tuple[float, Dict[str, Any]]] = []
        seen = set()
        for doc in candidates:
            doc_key = doc.get("doc_key") or str(doc.get("_id"))
            if doc_key in seen:
                continue
            seen.add(doc_key)
            doc_text = f"{doc.get('title', '')} {doc.get('summary', '')} {doc.get('content', '')}"
            doc_tokens = self._event_cluster_tokens(doc_text)
            token_overlap = event_tokens & doc_tokens
            title = str(doc.get("title") or "")
            score = 0.0
            if exact_key and doc.get("doc_key") == exact_key:
                score += 120.0
            if event_title and title and (event_title in title or title in event_title):
                score += 80.0
            score += min(50.0, 8.0 * len(token_overlap))
            symbol_overlap = mapped_symbols & set(doc.get("symbols") or [])
            score += 18.0 * len(symbol_overlap)
            if doc.get("source") == event.get("source"):
                score += 8.0
            # Themes are intentionally weak: they help rank already relevant docs,
            # but cannot pull unrelated evidence into an event analysis.
            theme_overlap = set(mapped_themes) & set(doc.get("themes") or [])
            score += min(8.0, 2.0 * len(theme_overlap))
            if score >= 16.0 or (exact_key and doc.get("doc_key") == exact_key):
                scored.append((score, doc))
        scored.sort(key=lambda item: (item[0], _parse_dt(item[1].get("published_at"))), reverse=True)
        return [doc for _, doc in scored[:limit]]

    def _event_analysis_prompt(self, event: Dict[str, Any], docs: List[Dict[str, Any]]) -> str:
        evidence_lines = []
        for doc in docs[:18]:
            metadata = doc.get("metadata") or {}
            lens = metadata.get("intel_lens") or metadata.get("public_source_category") or doc.get("document_type")
            evidence_lines.append(
                f"- [{doc.get('source')} / {lens}] {doc.get('title')} ({_jsonable(doc.get('published_at'))})"
            )
        category = event.get("source_category") or "market"
        lens = event.get("intel_lens") or "市场证据"
        return (
            f"事件: {event.get('title')}\n"
            f"地点: {event.get('location_name') or event.get('region')}\n"
            f"情报类别: {category} / {lens}\n"
            f"严重度: {event.get('severity')}\n"
            f"影响资产: {', '.join(event.get('affected_assets') or [])}\n"
            f"传导渠道: {', '.join(event.get('transmission_channels') or [])}\n"
            f"A股主题: {', '.join(event.get('mapped_themes') or [])}\n\n"
            "证据:\n" + "\n".join(evidence_lines) + "\n\n"
            "请按以下结构输出：1事件判断；2宏观变量/资产变量；3产业链和供应链传导；"
            "4受益/受损行业；5A股主题和个股观察；6证据强度与缺口；7是否price in；8交易确认条件；9失效条件。"
        )

    def _fallback_event_analysis(self, event: Dict[str, Any], docs: List[Dict[str, Any]]) -> str:
        themes = "、".join(event.get("mapped_themes") or []) or "等待主题映射"
        assets = "、".join(event.get("affected_assets") or []) or "等待资产映射"
        channels = "、".join(event.get("transmission_channels") or []) or "等待传导渠道确认"
        evidence = "\n".join(f"- {doc.get('title')}（{doc.get('source')}）" for doc in docs[:8]) or "- 暂无更多证据"
        return (
            f"## 事件判断\n{event.get('title')}\n\n"
            f"## 资产与变量\n{assets}\n\n"
            f"## 传导渠道\n{channels}\n\n"
            f"## A股主题\n{themes}\n\n"
            "## 个股映射\n等待资金、量价、公告和研报进一步确认。\n\n"
            "## 证据\n"
            f"{evidence}\n\n"
            "## 失效条件\n若后续新闻降温、相关商品/汇率未响应、A股映射行业无资金确认，则按低置信度处理。"
        )

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
                        "publish_time": _optional_dt(publish),
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
            title = str(item.get("title") or "").strip()
            content = str(item.get("content") or item.get("summary") or "").strip()
            if not title:
                continue
            published, published_quality = self._resolve_source_published_at(item, title=title, url=str(item.get("url") or ""))
            if published < window_start:
                continue
            text = f"{title} {content}"
            symbol = _normalize_code(item.get("symbol"))
            public_category = str(item.get("category") or item.get("source_category") or "").strip()
            public_profile = self._public_profile_for_category(public_category)
            matched_themes = self._match_themes(text)
            if public_profile:
                matched_themes = list(dict.fromkeys(matched_themes + list(public_profile.get("themes") or [])))
            docs.append(self._document(
                document_type=doc_type,
                title=title,
                content=content,
                source=str(item.get("source") or "未知来源"),
                url=str(item.get("url") or ""),
                published_at=published,
                symbols=[symbol] if symbol else [],
                themes=matched_themes,
                sentiment_score=_safe_float(item.get("sentiment_score"), _sentiment_score(text)),
                data_source=str(item.get("data_source") or "news"),
                metadata={
                    **{k: _jsonable(v) for k, v in item.items() if k not in {"title", "content", "summary"}},
                    "published_at_quality": published_quality,
                    "public_source": bool(public_profile),
                    "public_source_category": public_category or None,
                    "intel_lens": public_profile.get("label") if public_profile else None,
                    "affected_assets": list(public_profile.get("affected_assets") or []) if public_profile else [],
                    "transmission_channels": list(public_profile.get("transmission_channels") or []) if public_profile else [],
                },
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
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            content = str(item.get("content") or "")
            published, published_quality = self._resolve_source_published_at(item, title=title, url=str(item.get("url") or ""))
            if published < window_start:
                continue
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
                metadata={
                    **{k: _jsonable(v) for k, v in item.items() if k not in {"title", "content"}},
                    "published_at_quality": published_quality,
                },
            ))
        return docs

    def _resolve_source_published_at(self, item: Dict[str, Any], *, title: str, url: str) -> Tuple[datetime, str]:
        raw_fields = (
            "source_publish_time",
            "publish_time",
            "published_at",
            "发布日期",
            "发布时间",
            "date",
            "time",
            "showTime",
            "showtime",
            "publishDate",
            "publish_time",
            "ctime",
            "createTime",
            "updated_at",
        )
        explicit = next((_optional_dt(item.get(field)) for field in raw_fields if _optional_dt(item.get(field))), None)
        inferred = self._infer_published_at_from_url_or_title(url=url, title=title)
        now = now_tz().replace(tzinfo=None)
        if inferred and (not explicit or (abs((explicit - now).total_seconds()) < 600 and abs((explicit - inferred).total_seconds()) > 6 * 3600)):
            return self._clamp_future_published_at(inferred, "estimated_from_url_or_title")
        if explicit:
            return self._clamp_future_published_at(explicit, "source")
        if inferred:
            return self._clamp_future_published_at(inferred, "estimated_from_url_or_title")
        return now, "ingest_fallback"

    def _clamp_future_published_at(self, published_at: datetime, quality: str) -> Tuple[datetime, str]:
        now = now_tz().replace(tzinfo=None)
        if published_at > now + timedelta(minutes=30):
            return now, f"{quality}_future_clamped"
        return published_at, quality

    def _infer_published_at_from_url_or_title(self, *, url: str, title: str) -> Optional[datetime]:
        text = f"{url} {title}"
        match = re.search(r"/a/(\d{8})\d*\.html", url or "")
        year = month = day = None
        if match:
            raw = match.group(1)
            year, month, day = int(raw[:4]), int(raw[4:6]), int(raw[6:8])
        else:
            title_match = re.search(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日", title or "")
            if title_match:
                year = int(title_match.group(1) or now_tz().year)
                month = int(title_match.group(2))
                day = int(title_match.group(3))
        if not all([year, month, day]):
            return None
        hour = 18 if any(word in text for word in ("晚间", "晚报", "收盘", "复盘")) else 9
        try:
            inferred = datetime(int(year), int(month), int(day), hour, 0, 0)
        except Exception:
            return None
        if inferred > now_tz().replace(tzinfo=None) + timedelta(hours=2):
            return datetime(int(year), int(month), int(day), 9, 0, 0)
        return inferred

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
        stable_identity = url.strip() or f"{document_type}|{source}|{title}|{','.join(sorted(symbols))}"
        doc_key = hashlib.sha1(stable_identity.encode("utf-8")).hexdigest()
        source_weight = max(SOURCE_WEIGHTS.get(source, SOURCE_WEIGHTS.get(data_source, 1.0)), 0.5)
        public_category = str((metadata or {}).get("public_source_category") or "")
        public_profile = self._public_profile_for_category(public_category)
        profile_bias = _safe_float(public_profile.get("severity_bias")) * 0.45 if public_profile else 0.0
        influence = min(100.0, 45 + len(content) / 25 + len(themes) * 6 + source_weight * 8 + profile_bias)
        ingested_at = _utc_now()
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
            "first_seen_at": ingested_at,
            "ingested_at": ingested_at,
            "symbols": [s for s in symbols if s],
            "themes": themes,
            "sentiment": _sentiment_label(sentiment_score),
            "sentiment_score": sentiment_score,
            "source_weight": source_weight,
            "influence_score": round(influence, 2),
            "metadata": metadata,
        }

    async def _save_documents(self, documents: List[Dict[str, Any]]) -> Tuple[int, Dict[str, int]]:
        saved = 0
        saved_by_source: Dict[str, int] = {}
        for doc in documents:
            existing = await self.db.market_documents.find_one(
                {"doc_key": doc["doc_key"]},
                {"published_at": 1, "first_seen_at": 1, "ingested_at": 1, "metadata": 1},
            )
            if existing:
                quality = ((doc.get("metadata") or {}).get("published_at_quality") or "")
                if quality == "ingest_fallback" and existing.get("published_at"):
                    doc["published_at"] = existing["published_at"]
                doc["first_seen_at"] = existing.get("first_seen_at") or existing.get("ingested_at") or doc.get("first_seen_at")
            result = await self.db.market_documents.replace_one(
                {"doc_key": doc["doc_key"]},
                doc,
                upsert=True,
            )
            if result.upserted_id or result.modified_count:
                saved += 1
                source = str(doc.get("source") or doc.get("data_source") or "未知来源")
                saved_by_source[source] = saved_by_source.get(source, 0) + 1
        return saved, saved_by_source

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
            public_profile = self._public_profile_for_doc(doc)
            if not self._looks_global_event(text) and not public_profile:
                continue
            public_rule = self._public_rule_for_doc(doc, text, public_profile)
            rule = public_rule or self._geo_rule_for_text(text)
            if not rule:
                continue
            severity = self._event_severity(text, doc, rule)
            focus_score, focus_breakdown = self._event_focus_score(severity=severity, doc=doc, rule=rule)
            event_id = hashlib.sha1(
                f"{doc.get('doc_key')}|{rule['name']}".encode("utf-8")
            ).hexdigest()[:24]
            event_themes = sorted(set(rule.get("themes", []) + doc.get("themes", [])))
            metadata = doc.get("metadata") or {}
            event = {
                "event_id": event_id,
                "event_type": rule.get("event_type") or self._event_type(text),
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
                "source_weight": _safe_float(doc.get("source_weight"), 1.0),
                "influence_score": _safe_float(doc.get("influence_score")),
                "focus_score": focus_score,
                "score_breakdown": focus_breakdown,
                "affected_assets": rule.get("affected_assets", []),
                "transmission_channels": rule.get("transmission_channels", []),
                "mapped_themes": event_themes,
                "mapped_stocks": doc.get("symbols", []),
                "map_layers": self._event_layers_for_event(text, doc, rule),
                "document_key": doc.get("doc_key"),
                "source_category": metadata.get("public_source_category"),
                "intel_lens": metadata.get("intel_lens"),
                "evidence_kind": "public_intel" if public_profile else "market_evidence",
            }
            events.append(event)
        events.sort(key=lambda item: (_safe_float(item.get("severity")), _parse_dt(item.get("published_at"))), reverse=True)
        return events

    def _public_profile_for_category(self, category: Any) -> Optional[Dict[str, Any]]:
        key = str(category or "").strip()
        if not key:
            return None
        return PUBLIC_INTEL_CATEGORY_PROFILES.get(key)

    def _public_profile_for_doc(self, doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        metadata = doc.get("metadata") or {}
        category = metadata.get("public_source_category") or metadata.get("category")
        if not category and str(doc.get("data_source") or "").startswith("public_"):
            category = metadata.get("source_category")
        return self._public_profile_for_category(category)

    def _public_rule_for_doc(
        self,
        doc: Dict[str, Any],
        text: str,
        profile: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not profile:
            return None
        hint = self._location_hint_for_text(text)
        name = hint.get("name") if hint else profile.get("label")
        detected_event_type = self._event_type(text)
        event_type = profile.get("event_type") or detected_event_type
        if detected_event_type != "global_news" and event_type in {"macro", "geopolitical", "global_news"}:
            event_type = detected_event_type
        rule = {
            "keywords": [],
            "name": f"{profile.get('label')} · {name}",
            "lat": hint.get("lat") if hint else profile.get("lat"),
            "lon": hint.get("lon") if hint else profile.get("lon"),
            "region": hint.get("region") if hint else profile.get("region"),
            "country": hint.get("country") if hint else profile.get("country"),
            "affected_assets": profile.get("affected_assets", []),
            "transmission_channels": profile.get("transmission_channels", []),
            "themes": profile.get("themes", []),
            "severity_bias": profile.get("severity_bias", 0),
            "event_type": event_type,
        }
        if rule.get("lat") is None or rule.get("lon") is None:
            return None
        return rule

    def _location_hint_for_text(self, text: str) -> Optional[Dict[str, Any]]:
        normalized = text or ""
        for hint in LOCATION_HINTS:
            if any(keyword and keyword.lower() in normalized.lower() for keyword in hint.get("keywords", [])):
                return hint
        return None

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
        if any(word.lower() in text.lower() for word in ["ransomware", "cve", "vulnerability", "exploit", "cyber", "勒索", "漏洞", "网络攻击"]):
            return "cyber"
        if any(word.lower() in text.lower() for word in ["bitcoin", "stablecoin", "crypto", "defi", "加密", "稳定币", "比特币"]):
            return "crypto_financial"
        if any(word.lower() in text.lower() for word in ["ai", "artificial intelligence", "semiconductor", "chip", "startup", "launches"]):
            return "tech_supply_chain"
        if any(word.lower() in text.lower() for word in ["who", "cdc", "disease", "outbreak", "health", "疫情", "公共卫生"]):
            return "health"
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

    def _event_focus_score(self, *, severity: float, doc: Dict[str, Any], rule: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
        published_at = _parse_dt(doc.get("published_at"))
        age_hours = max(0.0, (_utc_now() - published_at).total_seconds() / 3600)
        recency_score = max(0.0, min(100.0, 100.0 * math.exp(-age_hours / 36.0)))
        source_impact = max(0.0, min(100.0, _safe_float(doc.get("influence_score"))))
        a_share_mapping = min(100.0, len(rule.get("themes") or []) * 18 + len(doc.get("symbols") or []) * 14)
        confidence_score = 72 if rule.get("country") != "待定位" else 46
        focus_score = (
            _safe_float(severity) * 0.42
            + source_impact * 0.24
            + recency_score * 0.14
            + a_share_mapping * 0.12
            + confidence_score * 0.08
        )
        return round(max(0.0, min(100.0, focus_score)), 2), {
            "formula": "42%事件严重度 + 24%来源/内容影响力 + 14%时效性 + 12%A股映射强度 + 8%定位置信度",
            "input_values": {
                "severity": round(_safe_float(severity), 2),
                "source_impact": round(source_impact, 2),
                "source_weight": round(_safe_float(doc.get("source_weight"), 1.0), 2),
                "influence_score": round(_safe_float(doc.get("influence_score")), 2),
                "recency_score": round(recency_score, 2),
                "age_hours": round(age_hours, 2),
                "a_share_mapping": round(a_share_mapping, 2),
                "theme_count": len(rule.get("themes") or []),
                "symbol_count": len(doc.get("symbols") or []),
                "confidence_score": confidence_score,
            },
            "normalization_method": "时效用36小时指数衰减；来源影响力来自证据池source_weight与influence_score；最终分数限制在0-100",
        }

    def _event_layers_for_event(self, text: str, doc: Dict[str, Any], rule: Dict[str, Any]) -> List[str]:
        event_type = rule.get("event_type") or self._event_type(text)
        mapped_themes = set(rule.get("themes", []) + doc.get("themes", []))
        layer_ids: List[str] = []
        for layer in WORLD_MONITOR_LAYERS:
            event_types = set(layer.get("event_types") or [])
            themes = set(layer.get("themes") or [])
            if layer["id"] == "a_share_mapping" and (mapped_themes or doc.get("symbols")):
                layer_ids.append(layer["id"])
                continue
            if layer["id"] == "chokepoints":
                corridor_text = f"{text} {rule.get('name', '')} {rule.get('region', '')}"
                if any(self._event_mentions_corridor({"title": corridor_text}, corridor) for corridor in STRATEGIC_CORRIDORS):
                    layer_ids.append(layer["id"])
                continue
            if event_type in event_types:
                layer_ids.append(layer["id"])
                continue
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
        doc_limit = 1200 if hours >= 120 else 500
        event_limit = 300 if hours >= 120 else 140
        documents = await self.db.market_documents.find(
            {"published_at": {"$gte": cutoff}}
        ).sort("published_at", -1).limit(doc_limit).to_list(length=doc_limit)
        events = await self.db.global_events.find(
            {"published_at": {"$gte": cutoff}}
        ).sort("published_at", -1).limit(event_limit).to_list(length=event_limit)
        events = [self._ensure_event_layers(event) for event in events]
        theme_nodes = self._build_theme_heatmap(documents, events)
        stock_opportunities = await self._build_stock_opportunities(documents, theme_nodes, events)
        return {"theme_heatmap_nodes": theme_nodes, "stock_opportunities": stock_opportunities}

    def _ensure_event_layers(self, event: Dict[str, Any]) -> Dict[str, Any]:
        enriched = dict(event)
        event_type = str(enriched.get("event_type") or "")
        mapped_themes = set(enriched.get("mapped_themes") or [])
        layer_ids: List[str] = []
        for layer in WORLD_MONITOR_LAYERS:
            if layer["id"] == "a_share_mapping" and (mapped_themes or enriched.get("mapped_stocks")):
                layer_ids.append(layer["id"])
                continue
            if layer["id"] == "chokepoints":
                if self._matches_corridor(enriched):
                    layer_ids.append(layer["id"])
                continue
            if event_type in set(layer.get("event_types") or []):
                layer_ids.append(layer["id"])
                continue
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
                "source_category": event.get("source_category"),
                "intel_lens": event.get("intel_lens"),
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
                public_categories = set(group.get("public_categories") or [])
                records = []
                for doc in documents:
                    if doc.get("document_type") not in doc_types:
                        continue
                    if public_categories:
                        category = (doc.get("metadata") or {}).get("public_source_category")
                        if category not in public_categories:
                            continue
                    records.append(doc)

            publish_times = [_parse_dt(record.get("published_at")) for record in records if record.get("published_at")]
            newest = max(publish_times) if publish_times else None
            oldest = min(publish_times) if publish_times else None
            age_minutes = max(0, int((now - newest).total_seconds() // 60)) if newest else None
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
                "source_count": len({
                    str(record.get("source") or record.get("data_source") or "unknown")
                    for record in records
                }),
                "category_counts": self._source_category_counts(records),
                "newest_item_at": newest,
                "oldest_item_at": oldest,
                "max_content_age_min": max_age,
                "age_minutes": age_minutes,
                "failed_datasets": [],
                "source_version": "market-intelligence-v1",
            })
        return envelopes

    def _source_category_counts(self, records: List[Dict[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for record in records:
            metadata = record.get("metadata") or {}
            category = str(metadata.get("public_source_category") or record.get("event_type") or record.get("document_type") or "unknown")
            counts[category] = counts.get(category, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True)[:8])

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
            heat_raw = len(related_docs) + len(related_events) * 1.6
            heat = _sigmoid_score(heat_raw, midpoint=4.0, scale=3.0)
            sentiment_avg = sum(_safe_float(doc.get("sentiment_score")) for doc in related_docs) / max(len(related_docs), 1)
            sentiment_component = max(0.0, min(100.0, 50 + sentiment_avg * 50))
            influence_avg = sum(_safe_float(doc.get("influence_score")) for doc in related_docs) / max(len(related_docs), 1)
            severity = max([_safe_float(e.get("severity")) for e in related_events] or [0])
            novelty = _sigmoid_score(len({doc.get("source") for doc in related_docs}) + len(related_events), midpoint=2.0, scale=1.8)
            score = max(0.0, min(100.0, (
                heat * 0.32
                + sentiment_component * 0.18
                + min(100, influence_avg) * 0.18
                + novelty * 0.14
                + severity * 0.18
            )))
            nodes.append({
                "name": theme,
                "value": round(max(8.0, score), 2),
                "score": round(score, 2),
                "heat": round(heat, 2),
                "sentiment_score": round(sentiment_avg, 3),
                "news_count": len(related_docs),
                "event_count": len(related_events),
                "risk_score": round(severity, 2),
                "trend": "up" if sentiment_avg >= 0.12 else "down" if sentiment_avg <= -0.12 else "watch",
                "keywords": keywords[:8],
                "headlines": [doc.get("title") for doc in related_docs[:4]],
                "score_breakdown": {
                    "formula": "32%热度 + 18%情绪 + 18%来源影响力 + 14%新颖度 + 18%事件严重度",
                    "input_values": {
                        "doc_count": len(related_docs),
                        "event_count": len(related_events),
                        "heat_component": round(heat, 2),
                        "sentiment_component": round(sentiment_component, 2),
                        "influence_component": round(min(100, influence_avg), 2),
                        "novelty_component": round(novelty, 2),
                        "severity_component": round(severity, 2),
                    },
                    "normalization_method": "热度和新颖度使用sigmoid标准化，避免数量堆积直接打满100",
                },
            })
        nodes.sort(key=lambda item: item["score"], reverse=True)
        return nodes[:18]

    async def _build_stock_opportunities(
        self,
        documents: List[Dict[str, Any]],
        themes: List[Dict[str, Any]],
        events: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        theme_score = {theme["name"]: _finite_float(theme.get("score")) for theme in themes}
        active_theme_names = [theme.get("name") for theme in themes[:8] if theme.get("name")]
        event_theme_scores: Dict[str, float] = {}
        event_mapped_stocks: Dict[str, List[Dict[str, Any]]] = {}
        for event in events or []:
            severity = _finite_float(event.get("severity"))
            for theme in event.get("mapped_themes") or []:
                event_theme_scores[theme] = max(event_theme_scores.get(theme, 0.0), severity)
            for code in event.get("mapped_stocks") or []:
                clean = _normalize_code(code)
                if clean:
                    event_mapped_stocks.setdefault(clean, []).append(event)
        active_theme_names = list(dict.fromkeys(active_theme_names + sorted(event_theme_scores, key=event_theme_scores.get, reverse=True)))
        if not active_theme_names:
            active_theme_names = list(THEME_KEYWORDS.keys())

        by_code: Dict[str, Dict[str, Any]] = {}

        def ensure_item(code: str) -> Optional[Dict[str, Any]]:
            clean = _normalize_code(code)
            if not clean:
                return None
            item = by_code.setdefault(clean, {
                "code": clean,
                "name": "",
                "industry": "",
                "theme": "",
                "matched_themes": [],
                "identity_themes": [],
                "universe_sources": [],
                "universe_reasons": [],
                "raw_evidence_score": 0.0,
                "news_count": 0,
                "comment_count": 0,
                "research_count": 0,
                "announcement_count": 0,
                "quant_count": 0,
                "sentiment_total": 0.0,
                "sentiment_docs": 0,
                "sentiment_score": 0.0,
                "funds_score": 42.0,
                "price_score": 45.0,
                "long_term_score": 45.0,
                "event_exposure_score": 35.0,
                "evidence_score": 35.0,
                "social_score": 35.0,
                "supply_chain_score": 42.0,
                "risk_score": 0.0,
                "headlines": [],
                "documents": [],
                "linked_events": [],
            })
            return item

        def add_source(item: Dict[str, Any], source: str, reason: str) -> None:
            if source and source not in item["universe_sources"]:
                item["universe_sources"].append(source)
            if reason and reason not in item["universe_reasons"] and len(item["universe_reasons"]) < 6:
                item["universe_reasons"].append(reason)

        for doc in documents:
            doc_symbols = [_normalize_code(code) for code in doc.get("symbols", [])]
            doc_symbols = [code for code in doc_symbols if code]
            for code in doc_symbols:
                item = ensure_item(code)
                if not item:
                    continue
                add_source(item, "直接证据", "新闻/评论/研报/公告证据池直接提及该股票")
                doc_type = doc.get("document_type")
                item["news_count"] += 1 if doc_type in {"news", "stock_news"} else 0
                item["comment_count"] += 1 if doc_type == "social_comment" else 0
                item["research_count"] += 1 if doc_type == "research_report" else 0
                item["announcement_count"] += 1 if doc_type == "announcement" else 0
                item["quant_count"] += 1 if doc_type == "quant_signal" else 0
                item["sentiment_total"] += _finite_float(doc.get("sentiment_score"))
                item["sentiment_docs"] += 1
                item["raw_evidence_score"] += 1 + _finite_float(doc.get("influence_score")) / 100
                for theme in doc.get("themes", []):
                    if theme not in item["matched_themes"]:
                        item["matched_themes"].append(theme)
                    item["raw_evidence_score"] += theme_score.get(theme, 0) / 100
                if len(item["headlines"]) < 5:
                    item["headlines"].append(doc.get("title"))
                if len(item["documents"]) < 10:
                    item["documents"].append(_jsonable(doc))

        for code, mapped_events in event_mapped_stocks.items():
            item = ensure_item(code)
            if not item:
                continue
            add_source(item, "全球事件映射", "全球事件显式映射到该股票")
            item["linked_events"].extend(_jsonable(event) for event in mapped_events[:4])
            for event in mapped_events:
                for theme in event.get("mapped_themes") or []:
                    if theme not in item["matched_themes"]:
                        item["matched_themes"].append(theme)

        quote_projection = {
            "_id": 0,
            "code": 1,
            "symbol": 1,
            "name": 1,
            "pct_chg": 1,
            "amount": 1,
            "volume": 1,
            "close": 1,
            "price": 1,
            "updated_at": 1,
        }
        quotes = await self.db.market_quotes.find({}, quote_projection).sort("amount", -1).limit(6200).to_list(length=6200)
        quote_by_code: Dict[str, Dict[str, Any]] = {}
        for quote in quotes:
            code = _normalize_code(quote.get("code") or quote.get("symbol"))
            if not code:
                continue
            quote_by_code[code] = quote
            item = ensure_item(code)
            if not item:
                continue
            add_source(item, "全市场行情", "来自 market_quotes 全市场行情池，不再只看涨幅榜")
            item["name"] = quote.get("name") or item["name"]
            pct = _finite_float(quote.get("pct_chg"))
            amount = _finite_float(quote.get("amount"))
            item["pct_chg"] = pct
            item["amount"] = amount
            item["volume"] = _finite_float(quote.get("volume"))
            item["price"] = _finite_float(quote.get("price") or quote.get("close"))
            item["price_score"] = self._price_structure_score(pct)
            item["funds_score"] = round(_sigmoid_score(amount / 1_000_000_000, midpoint=2.2, scale=2.0), 2) if amount else 42.0

        basic_projection = {
            "_id": 0,
            "code": 1,
            "symbol": 1,
            "name": 1,
            "industry": 1,
            "market": 1,
            "area": 1,
            "total_mv": 1,
            "circ_mv": 1,
            "pe": 1,
            "pe_ttm": 1,
            "pb": 1,
            "pb_mrq": 1,
            "ps": 1,
            "turnover_rate": 1,
            "volume_ratio": 1,
            "list_date": 1,
        }
        basics = await self.db.stock_basic_info.find({}, basic_projection).limit(7000).to_list(length=7000)
        basic_by_code: Dict[str, Dict[str, Any]] = {}
        for basic in basics:
            code = _normalize_code(basic.get("code") or basic.get("symbol"))
            if not code:
                continue
            basic_by_code[code] = basic
            item = ensure_item(code)
            if not item:
                continue
            add_source(item, "全市场基础库", "来自 stock_basic_info 全市场基础库")
            item["name"] = basic.get("name") or item["name"]
            item["industry"] = basic.get("industry") or basic.get("market") or item["industry"]
            inferred_themes = self._infer_stock_themes(basic, quote_by_code.get(code, {}), list(THEME_KEYWORDS.keys()))
            item["identity_themes"] = list(dict.fromkeys((item.get("identity_themes") or []) + inferred_themes))
            for theme in inferred_themes:
                if theme not in item["matched_themes"]:
                    item["matched_themes"].append(theme)
            if inferred_themes:
                add_source(item, "事件/主题产业链", f"公司行业/名称匹配当前主题：{','.join(inferred_themes[:3])}")

        result: List[Dict[str, Any]] = []
        methodology = self._stock_methodology()
        for code, item in by_code.items():
            basic = basic_by_code.get(code, {})
            quote = quote_by_code.get(code, {})
            name_text = str(item.get("name") or basic.get("name") or quote.get("name") or "")
            if not self._is_a_share_candidate(code, name_text):
                continue
            item["matched_themes"] = [theme for theme in item["matched_themes"] if theme in THEME_KEYWORDS]
            if not item["matched_themes"]:
                item["matched_themes"] = self._infer_stock_themes(basic, quote, active_theme_names)
            if item["matched_themes"]:
                primary_pool = item.get("identity_themes") or item["matched_themes"]
                item["theme"] = max(
                    primary_pool,
                    key=lambda theme: theme_score.get(theme, 38.0) + event_theme_scores.get(theme, 0.0) * (0.25 if item.get("identity_themes") else 1.0),
                )
            else:
                item["theme"] = item.get("industry") or "未映射"

            evidence_count = (
                item["news_count"]
                + item["comment_count"]
                + item["research_count"]
                + item["announcement_count"]
                + item["quant_count"]
            )
            sentiment_divisor = max(item["sentiment_docs"], 1)
            item["sentiment_score"] = round(item["sentiment_total"] / sentiment_divisor, 3)
            sentiment_component = max(0.0, min(100.0, 50 + item["sentiment_score"] * 50))
            item["evidence_score"] = round(max(
                32.0,
                _sigmoid_score(
                    item["news_count"]
                    + item["research_count"] * 1.7
                    + item["announcement_count"] * 2.0
                    + item["quant_count"] * 1.3
                    + item["raw_evidence_score"] * 0.7,
                    midpoint=4.5,
                    scale=3.4,
                ),
            ), 2)
            item["social_score"] = round(
                _sigmoid_score(item["comment_count"], midpoint=18.0, scale=12.0)
                if item["comment_count"]
                else 38.0,
                2,
            )
            event_exposure = self._stock_event_exposure_score(item["matched_themes"], event_theme_scores, event_mapped_stocks.get(code, []))
            item["event_exposure_score"] = round(event_exposure, 2)
            theme_component = max(
                [theme_score.get(theme, 38.0) for theme in item["matched_themes"]]
                + [event_exposure * 0.9, 35.0]
            )
            item["long_term_score"] = round(self._long_term_stock_score(basic, quote, item["matched_themes"]), 2)
            item["supply_chain_score"] = round(self._supply_chain_score(item["matched_themes"], event_theme_scores), 2)
            price_in_penalty = self._price_in_penalty(_finite_float(item.get("pct_chg")), evidence_count, item["event_exposure_score"])
            risk_score = self._stock_risk_score(item, basic, quote)
            item["risk_score"] = round(risk_score, 2)
            score = (
                item["long_term_score"] * 0.22
                + theme_component * 0.18
                + item["evidence_score"] * 0.14
                + item["social_score"] * 0.10
                + _finite_float(item.get("funds_score")) * 0.15
                + _finite_float(item.get("price_score")) * 0.11
                + item["supply_chain_score"] * 0.10
                - risk_score
                - price_in_penalty
            )
            item["price_in_penalty"] = round(price_in_penalty, 2)
            item["score"] = round(max(0, min(100, score)), 2)
            item["signal_strength"] = round(max(0, min(
                100,
                _finite_float(item.get("funds_score")) * 0.32
                + _finite_float(item.get("price_score")) * 0.26
                + item["evidence_score"] * 0.22
                + sentiment_component * 0.10
                + theme_component * 0.10
                - price_in_penalty * 0.35
                - risk_score * 0.25,
            )), 2)
            item["prediction_horizon"] = "中长线1-3个月；事件催化跟踪1-3个交易日"
            item["confidence"] = round(max(0.18, min(
                0.92,
                0.18
                + (0.16 if basic else 0)
                + (0.14 if quote else 0)
                + min(evidence_count, 16) / 16 * 0.20
                + min(len(item["matched_themes"]), 3) * 0.06
                + min(item["event_exposure_score"], 90) / 100 * 0.12,
            )), 3)
            item["candidate_scope"] = "事件推导+全市场扫描" if item["matched_themes"] else "全市场扫描"
            item["universe_source"] = " / ".join(item["universe_sources"][:4])
            item["candidate_reason"] = "；".join(item["universe_reasons"][:4])
            item["score_breakdown"] = {
                "formula": methodology["formula"],
                "input_values": {
                    "long_term_score": item["long_term_score"],
                    "theme_component": round(theme_component, 2),
                    "event_exposure_score": item["event_exposure_score"],
                    "news_research_announcement_evidence": item["evidence_score"],
                    "sentiment_component": round(sentiment_component, 2),
                    "social_score": item["social_score"],
                    "funds_score": item.get("funds_score", 0),
                    "price_score": item.get("price_score", 0),
                    "supply_chain_score": item["supply_chain_score"],
                    "risk_score": item["risk_score"],
                    "price_in_penalty": item["price_in_penalty"],
                    "evidence_count": evidence_count,
                    "matched_themes": item["matched_themes"],
                    "identity_themes": item.get("identity_themes", []),
                    "universe_sources": item["universe_sources"],
                    "candidate_scope": item["candidate_scope"],
                    "pct_chg": round(_finite_float(item.get("pct_chg")), 2),
                    "amount": round(_finite_float(item.get("amount")), 2),
                    "pe": _finite_float(basic.get("pe_ttm") or basic.get("pe")) if basic else None,
                    "pb": _finite_float(basic.get("pb_mrq") or basic.get("pb")) if basic else None,
                    "total_mv_yi": _finite_float(basic.get("total_mv")) if basic else None,
                },
                "normalization_method": methodology["normalization_method"],
            }
            item.pop("sentiment_total", None)
            item.pop("sentiment_docs", None)
            if not item["name"]:
                item["name"] = item["code"]
            result.append(item)

        result.sort(key=lambda item: (
            item["score"],
            item.get("event_exposure_score", 0),
            item.get("evidence_score", 0),
            item.get("signal_strength", 0),
        ), reverse=True)
        return result[:60]

    def _is_a_share_candidate(self, code: str, name: str) -> bool:
        if not re.fullmatch(r"\d{6}", code or ""):
            return False
        if code.startswith(("200", "900")):
            return False
        normalized_name = (name or "").upper()
        if "退" in normalized_name or normalized_name.startswith(("ST", "*ST", "SST")):
            return False
        return code.startswith(("000", "001", "002", "003", "300", "301", "600", "601", "603", "605", "688", "689", "430", "830", "831", "832", "833", "834", "835", "836", "837", "838", "839", "870", "871", "872", "873", "920"))

    def _infer_stock_themes(
        self,
        basic: Dict[str, Any],
        quote: Dict[str, Any],
        active_theme_names: List[str],
    ) -> List[str]:
        text = " ".join(
            str(value or "")
            for value in [
                basic.get("name"),
                quote.get("name"),
                basic.get("industry"),
                basic.get("market"),
                basic.get("area"),
            ]
        )
        themes: List[str] = []
        for theme in active_theme_names:
            keywords = list(THEME_KEYWORDS.get(theme, [])) + THEME_INDUSTRY_HINTS.get(theme, []) + PUBLIC_THEME_KEYWORDS.get(theme, [])
            if self._matches(text=text, keywords=keywords):
                themes.append(theme)
        return list(dict.fromkeys(themes))

    def _price_structure_score(self, pct: float) -> float:
        if pct == 0:
            return 48.0
        if pct >= 9.2:
            return 34.0
        if pct > 6.5:
            return round(max(35.0, 70.0 - (pct - 6.5) * 10.0), 2)
        if pct >= 0:
            return round(min(78.0, 52.0 + pct * 4.4), 2)
        return round(max(24.0, 50.0 + pct * 4.2), 2)

    def _price_in_penalty(self, pct: float, evidence_count: int, event_exposure_score: float) -> float:
        if pct <= 6.5:
            return 0.0
        fresh_catalyst_relief = min(0.45, evidence_count * 0.035 + event_exposure_score / 1000)
        penalty = (pct - 6.5) * 8.0 * (1 - fresh_catalyst_relief)
        if pct >= 9.2:
            penalty += 8.0 * (1 - fresh_catalyst_relief)
        return round(max(0.0, penalty), 2)

    def _stock_event_exposure_score(
        self,
        matched_themes: List[str],
        event_theme_scores: Dict[str, float],
        mapped_events: List[Dict[str, Any]],
    ) -> float:
        theme_severity = max([_finite_float(event_theme_scores.get(theme, 0.0)) for theme in matched_themes] or [0.0])
        direct_severity = max([_finite_float(event.get("severity")) for event in mapped_events] or [0.0])
        if not theme_severity and not direct_severity:
            return 35.0
        novelty = _sigmoid_score(len(matched_themes) + len(mapped_events), midpoint=2.0, scale=2.0)
        return max(35.0, min(100.0, max(theme_severity, direct_severity) * 0.72 + novelty * 0.28))

    def _supply_chain_score(self, matched_themes: List[str], event_theme_scores: Dict[str, float]) -> float:
        if not matched_themes:
            return 42.0
        strategic_themes = {"AI算力", "半导体", "新能源", "军工安全", "资源通胀", "消费出海", "机器人"}
        base = 50.0 + sum(4.0 for theme in matched_themes if theme in strategic_themes)
        event_boost = max([_finite_float(event_theme_scores.get(theme, 0.0)) for theme in matched_themes] or [0.0]) * 0.18
        return max(38.0, min(88.0, base + event_boost))

    def _long_term_stock_score(self, basic: Dict[str, Any], quote: Dict[str, Any], matched_themes: List[str]) -> float:
        if not basic and not quote:
            return 40.0
        total_mv = _finite_float(basic.get("total_mv") or basic.get("circ_mv"))
        pe = _finite_float(basic.get("pe_ttm") or basic.get("pe"))
        pb = _finite_float(basic.get("pb_mrq") or basic.get("pb"))
        turnover = _finite_float(basic.get("turnover_rate"))
        mv_component = 50.0
        if total_mv > 0:
            mv_component = _sigmoid_score(math.log10(total_mv + 1), midpoint=2.05, scale=0.38)
        pe_component = 52.0
        if pe > 0:
            pe_component = max(20.0, min(78.0, 74.0 - abs(pe - 28.0) * 0.85))
        pb_component = 52.0
        if pb > 0:
            pb_component = max(22.0, min(72.0, 68.0 - abs(pb - 3.0) * 5.5))
        turnover_component = 48.0
        if turnover > 0:
            turnover_component = max(35.0, min(70.0, 44.0 + min(turnover, 6.0) * 4.3))
        strategic_bonus = min(12.0, len(set(matched_themes).intersection({"AI算力", "半导体", "机器人", "新能源", "军工安全"})) * 4.0)
        return max(25.0, min(88.0, mv_component * 0.34 + pe_component * 0.22 + pb_component * 0.16 + turnover_component * 0.12 + 44.0 * 0.16 + strategic_bonus))

    def _stock_risk_score(self, item: Dict[str, Any], basic: Dict[str, Any], quote: Dict[str, Any]) -> float:
        risk = 0.0
        pct = _finite_float(item.get("pct_chg") or quote.get("pct_chg"))
        name = str(item.get("name") or basic.get("name") or quote.get("name") or "").upper()
        if item.get("sentiment_score", 0) < -0.32:
            risk += 10.0
        if pct <= -7:
            risk += 8.0
        if pct >= 9.2 and item.get("evidence_score", 0) < 60:
            risk += 7.0
        if "ST" in name or "退" in name:
            risk += 35.0
        if not item.get("amount") and quote:
            risk += 4.0
        return risk

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
                elif dim == "资金确认":
                    value = _sigmoid_score(_safe_float(theme.get("news_count")) + base / 20, midpoint=6, scale=3.5)
                elif dim == "量价共振":
                    value = max(0, min(100, base * 0.55 + _safe_float(theme.get("heat")) * 0.22))
                elif dim == "基本面":
                    value = max(0, min(100, 42 + len(theme.get("keywords") or []) * 2 + (8 if theme.get("event_count") else 0)))
                rows.append({
                    "theme": theme["name"],
                    "dimension": dim,
                    "value": round(min(100, max(0, value)), 2),
                    "score_breakdown": {
                        "formula": f"{dim}按主题真实新闻、事件、情绪、热度或基本面代理变量计算",
                        "input_values": {
                            "theme_score": base,
                            "news_count": theme.get("news_count", 0),
                            "event_count": theme.get("event_count", 0),
                            "sentiment_score": theme.get("sentiment_score", 0),
                            "heat": theme.get("heat", 0),
                        },
                        "normalization_method": "数量类用sigmoid，情绪类从[-1,1]映射到[0,100]，不使用固定档位造数",
                    },
                })
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
            "score_breakdown": {
                "formula": "ok_count / total * 100",
                "input_values": {"ok_count": ok_count, "total": total},
                "normalization_method": "核心源15分钟内成功抓取视为ok",
            },
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

    def _render_dashboard_markdown(
        self,
        summary: str,
        themes: List[Dict[str, Any]],
        stocks: List[Dict[str, Any]],
        chains: List[Dict[str, Any]],
        risks: List[str],
        source_envelopes: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
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
        if source_envelopes:
            lines.extend(["", "## 公共情报覆盖"])
            for source in source_envelopes:
                if not str(source.get("id") or "").startswith(("public_", "policy_", "cyber_", "supply_")):
                    continue
                category_counts = source.get("category_counts") or {}
                categories = ", ".join(f"{key}:{value}" for key, value in list(category_counts.items())[:4])
                lines.append(
                    f"- {source.get('label')}: {source.get('state')}，{source.get('record_count')} 条，"
                    f"{source.get('source_count', 0)} 个源；{categories or '暂无分类'}"
                )
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
        matched: List[str] = []
        for theme, keywords in THEME_KEYWORDS.items():
            expanded = list(keywords) + THEME_INDUSTRY_HINTS.get(theme, []) + PUBLIC_THEME_KEYWORDS.get(theme, [])
            if self._matches(text=text, keywords=expanded):
                matched.append(theme)
        return matched

    def _matches(self, *, text: str, keywords: Iterable[str]) -> bool:
        return any(keyword and keyword.lower() in (text or "").lower() for keyword in keywords)


_market_intelligence_service: Optional[MarketIntelligenceService] = None


async def get_market_intelligence_service() -> MarketIntelligenceService:
    global _market_intelligence_service
    if _market_intelligence_service is None:
        _market_intelligence_service = MarketIntelligenceService()
        await _market_intelligence_service._ensure_indexes()
    return _market_intelligence_service
