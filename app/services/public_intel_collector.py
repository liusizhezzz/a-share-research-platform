"""
Public-source intelligence collectors.

The collector intentionally sticks to official APIs, public RSS/Atom feeds, and
small-sample public HTML pages. It does not bypass logins, captchas, paywalls,
or robots restrictions.
"""
from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import feedparser
import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.services.investment_daily_service import (
    GLOBAL_KEYWORDS,
    MARKET_KEYWORDS,
    _parse_dt,
    _sentiment_label,
    _sentiment_score,
)

logger = logging.getLogger(__name__)


USER_AGENT = "TradingAgents-CN/1.0 personal-research public-source-monitor"


@dataclass(frozen=True)
class PublicSource:
    name: str
    category: str
    access: str
    url: str
    max_items: int = 8
    language: str = "en"
    country: str = "global"
    license_note: str = "Public metadata/feed/API; store excerpt and source URL only."
    enabled: bool = True


DIRECT_FEED_SOURCES: List[PublicSource] = [
    PublicSource("SEC Latest Filings", "official_finance", "feed", "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&output=atom", 10),
    PublicSource("Federal Reserve Press Releases", "macro", "feed", "https://www.federalreserve.gov/feeds/press_all.xml", 10, country="US"),
    PublicSource("GitHub Blog", "tech", "feed", "https://github.blog/feed/", 8),
    PublicSource("arXiv AI", "research", "feed", "https://export.arxiv.org/api/query?search_query=cat:cs.AI&start=0&max_results=10", 10),
    PublicSource("CNBC Markets", "markets_news", "feed", "https://www.cnbc.com/id/100003114/device/rss/rss.html", 12),
    PublicSource("BBC World", "world_news", "feed", "https://feeds.bbci.co.uk/news/world/rss.xml", 12),
    PublicSource("Al Jazeera", "world_news", "feed", "https://www.aljazeera.com/xml/rss/all.xml", 12),
    PublicSource("DW News", "world_news", "feed", "https://rss.dw.com/xml/rss-en-all", 10),
    PublicSource("France 24", "world_news", "feed", "https://www.france24.com/en/rss", 10),
    PublicSource("Guardian World", "world_news", "feed", "https://www.theguardian.com/world/rss", 12),
    PublicSource("NPR News", "world_news", "feed", "https://feeds.npr.org/1001/rss.xml", 10),
    PublicSource("CSIS", "think_tank", "feed", "https://www.csis.org/rss.xml", 8),
    PublicSource("Atlantic Council", "think_tank", "feed", "https://www.atlanticcouncil.org/feed/", 8),
    PublicSource("Brookings", "think_tank", "feed", "https://www.brookings.edu/feed/", 8),
    PublicSource("Defense News", "defense", "feed", "https://www.defensenews.com/arc/outboundfeeds/rss/", 8),
    PublicSource("Defense One", "defense", "feed", "https://www.defenseone.com/rss/all/", 8),
    PublicSource("USNI News", "defense", "feed", "https://news.usni.org/feed", 8),
    PublicSource("War on the Rocks", "defense", "feed", "https://warontherocks.com/feed/", 8),
    PublicSource("Bellingcat", "osint", "feed", "https://www.bellingcat.com/feed/", 8),
    PublicSource("gCaptain", "maritime", "feed", "https://gcaptain.com/feed/", 8),
    PublicSource("TechCrunch", "startups", "feed", "https://techcrunch.com/feed/", 8),
    PublicSource("The Verge AI", "tech", "feed", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", 8),
    PublicSource("VentureBeat AI", "tech", "feed", "https://venturebeat.com/category/ai/feed/", 8),
    PublicSource("Layoffs.fyi", "layoffs", "feed", "https://layoffs.fyi/feed/", 8),
]


DIRECT_JSON_SOURCES: List[PublicSource] = [
    PublicSource("CFTC COT", "positioning", "json", "https://publicreporting.cftc.gov/resource/6dca-aqww.json?$limit=12", 12),
    PublicSource("CISA KEV JSON", "cyber", "json", "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json", 12, country="US"),
    PublicSource("NVD CVE API", "cyber", "json", "https://services.nvd.nist.gov/rest/json/cves/2.0?resultsPerPage=12", 12, country="US"),
    PublicSource("Ransomware Live", "cyber", "json", "https://api.ransomware.live/v2/recentvictims", 12),
    PublicSource("UNHCR Countries API", "displacement", "json", "https://api.unhcr.org/population/v1/countries/?limit=20", 8),
    PublicSource("CoinGecko Markets", "crypto", "json", "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&per_page=20&page=1", 20),
    PublicSource("DefiLlama Stablecoins", "crypto", "json", "https://stablecoins.llama.fi/stablecoins?includePrices=true", 12),
    PublicSource("GDELT DOC 2.1", "global_news", "json", "https://api.gdeltproject.org/api/v2/doc/doc?query=geopolitics&mode=artlist&format=json&maxrecords=20", 20),
    PublicSource("Hacker News Top Stories", "tech", "json_hn", "https://hacker-news.firebaseio.com/v0/topstories.json", 10),
    PublicSource("YC Launches", "startups", "json_yc", "https://www.ycombinator.com/launches", 12),
]


PUBLIC_HTML_SOURCES: List[PublicSource] = [
    PublicSource("US Treasury Press Releases", "macro", "html", "https://home.treasury.gov/news/press-releases", 8, country="US"),
    PublicSource("WHO Disease Outbreak News", "health", "html", "https://www.who.int/emergencies/disease-outbreak-news", 8),
    PublicSource("CDC Newsroom", "health", "html", "https://www.cdc.gov/media/releases/index.html", 8, country="US"),
    PublicSource("FAO News", "food", "html", "https://www.fao.org/newsroom/en/", 8),
    PublicSource("Sina Finance", "china_finance", "html", "https://finance.sina.com.cn/", 10, language="zh", country="CN"),
]


class PublicIntelCollector:
    """Fetch public-source items for market intelligence ingestion."""

    def __init__(self) -> None:
        self.timeout = float(settings.MARKET_INTELLIGENCE_PUBLIC_SOURCE_TIMEOUT_SECONDS)
        self.max_sources = int(settings.MARKET_INTELLIGENCE_PUBLIC_SOURCE_MAX_SOURCES)
        self.max_items_per_source = int(settings.MARKET_INTELLIGENCE_PUBLIC_SOURCE_MAX_ITEMS)
        self.include_html = bool(settings.MARKET_INTELLIGENCE_PUBLIC_SOURCE_INCLUDE_HTML)

    async def collect(self, *, window_start: datetime) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        sources = [*DIRECT_FEED_SOURCES, *DIRECT_JSON_SOURCES]
        if self.include_html:
            sources.extend(PUBLIC_HTML_SOURCES)
        sources = [source for source in sources if source.enabled][: self.max_sources]

        semaphore = asyncio.Semaphore(max(1, settings.MARKET_INTELLIGENCE_PUBLIC_SOURCE_CONCURRENCY))
        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            follow_redirects=True,
            trust_env=False,
        ) as client:
            tasks = [self._collect_source(client, semaphore, source, window_start) for source in sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        items: List[Dict[str, Any]] = []
        statuses: List[Dict[str, Any]] = []
        for source, result in zip(sources, results):
            if isinstance(result, Exception):
                statuses.append(self._status(source, False, 0, f"{type(result).__name__}: {result}"))
                continue
            source_items, status = result
            items.extend(source_items)
            statuses.append(status)
        return self._dedupe(items), statuses

    async def _collect_source(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        source: PublicSource,
        window_start: datetime,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        async with semaphore:
            try:
                if source.access == "html":
                    allowed = await self._robots_allows(client, source.url)
                    if not allowed:
                        return [], self._status(source, False, 0, "blocked_by_robots")
                response = await client.get(source.url)
                if response.status_code == 429:
                    return [], self._status(source, False, 0, "rate_limited_429")
                if response.status_code in {401, 402, 403}:
                    return [], self._status(source, False, 0, f"requires_review_or_authorization_{response.status_code}")
                response.raise_for_status()

                if source.access == "feed":
                    items = self._parse_feed(source, response.content, window_start)
                elif source.access == "json_hn":
                    items = await self._parse_hacker_news(client, source, response.json(), window_start)
                elif source.access == "json_yc":
                    items = self._parse_yc_launches(source, response.text, window_start)
                elif source.access == "json":
                    items = self._parse_json(source, response.json(), window_start)
                elif source.access == "html":
                    items = self._parse_html_links(source, response.text, window_start)
                else:
                    items = []
                items = items[: min(source.max_items, self.max_items_per_source)]
                latest = max((item.get("publish_time") for item in items if item.get("publish_time")), default=None)
                return items, self._status(source, True, len(items), "ok" if items else "empty", latest)
            except Exception as exc:
                logger.debug("公开源采集失败 %s: %s", source.name, exc)
                return [], self._status(source, False, 0, f"{type(exc).__name__}: {exc}")

    def _parse_feed(self, source: PublicSource, body: bytes, window_start: datetime) -> List[Dict[str, Any]]:
        parsed = feedparser.parse(body)
        items: List[Dict[str, Any]] = []
        for entry in parsed.entries[: self.max_items_per_source]:
            title = self._clean(entry.get("title") or "")
            link = str(entry.get("link") or "")
            summary = self._clean(entry.get("summary") or entry.get("description") or "")
            published = self._entry_datetime(entry) or _parse_dt(None)
            if published < window_start or not title:
                continue
            items.append(self._item(source, title, summary, link, published, raw=entry))
        return items

    async def _parse_hacker_news(
        self,
        client: httpx.AsyncClient,
        source: PublicSource,
        ids: Any,
        window_start: datetime,
    ) -> List[Dict[str, Any]]:
        if not isinstance(ids, list):
            return []
        tasks = [client.get(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json") for item_id in ids[: source.max_items]]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        items: List[Dict[str, Any]] = []
        for response in responses:
            if isinstance(response, Exception) or response.status_code != 200:
                continue
            data = response.json()
            title = self._clean(data.get("title") or "")
            if not title:
                continue
            published = datetime.fromtimestamp(float(data.get("time") or 0), tz=timezone.utc).replace(tzinfo=None)
            if published < window_start:
                continue
            url = str(data.get("url") or f"https://news.ycombinator.com/item?id={data.get('id')}")
            content = f"score={data.get('score', 0)} descendants={data.get('descendants', 0)}"
            items.append(self._item(source, title, content, url, published, raw=data))
        return items

    def _parse_yc_launches(self, source: PublicSource, text: str, window_start: datetime) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(text, "html.parser")
        now = datetime.utcnow()
        items: List[Dict[str, Any]] = []
        for anchor in soup.select("a[href]"):
            href = str(anchor.get("href") or "")
            label = self._clean(anchor.get_text(" ", strip=True))
            if "/launches/" not in href or len(label) < 4:
                continue
            url = urljoin(source.url, href)
            items.append(self._item(source, label[:180], "YC Launches public listing metadata.", url, now, raw={"href": href}))
            if len(items) >= source.max_items:
                break
        return [item for item in items if item["publish_time"] >= window_start]

    def _parse_json(self, source: PublicSource, data: Any, window_start: datetime) -> List[Dict[str, Any]]:
        if source.name == "CISA KEV JSON":
            records = data.get("vulnerabilities", []) if isinstance(data, dict) else []
            return [self._json_item(source, rec, window_start, "cveID", "vulnerabilityName", "dateAdded") for rec in records]
        if source.name == "NVD CVE API":
            records = data.get("vulnerabilities", []) if isinstance(data, dict) else []
            items = []
            for rec in records:
                cve = rec.get("cve", {}) if isinstance(rec, dict) else {}
                title = cve.get("id") or "NVD CVE"
                descriptions = cve.get("descriptions") or []
                content = next((d.get("value") for d in descriptions if d.get("lang") == "en"), "")
                published = _parse_dt(cve.get("published"))
                if published >= window_start:
                    items.append(self._item(source, title, content, f"https://nvd.nist.gov/vuln/detail/{title}", published, raw=cve))
            return items
        if source.name == "Ransomware Live":
            records = data if isinstance(data, list) else data.get("victims", []) if isinstance(data, dict) else []
            return [self._json_item(source, rec, window_start, "victim", "activity", "discovered") for rec in records]
        if source.name == "CFTC COT":
            records = data if isinstance(data, list) else []
            return [self._json_item(source, rec, window_start, "market_and_exchange_names", "commodity_name", "report_date_as_yyyy_mm_dd") for rec in records]
        if source.name == "UNHCR Countries API":
            records = data.get("items", []) if isinstance(data, dict) else []
            return [self._json_item(source, rec, window_start, "name", "iso3", None) for rec in records]
        if source.name == "CoinGecko Markets":
            records = data if isinstance(data, list) else []
            items = []
            now = datetime.utcnow()
            for rec in records:
                name = rec.get("name") or rec.get("symbol") or "crypto asset"
                change = rec.get("price_change_percentage_24h")
                title = f"{name} crypto market snapshot: {change if change is not None else '-'}% 24h"
                content = f"price={rec.get('current_price')} market_cap={rec.get('market_cap')} volume={rec.get('total_volume')}"
                items.append(self._item(source, title, content, f"https://www.coingecko.com/en/coins/{rec.get('id')}", now, raw=rec))
            return [item for item in items if item["publish_time"] >= window_start]
        if source.name == "DefiLlama Stablecoins":
            records = data.get("peggedAssets", []) if isinstance(data, dict) else []
            now = datetime.utcnow()
            items = []
            for rec in records[: source.max_items]:
                title = f"{rec.get('name') or rec.get('symbol') or 'Stablecoin'} stablecoin supply snapshot"
                content = f"circulating={rec.get('circulating')} peggedUSD={rec.get('circulating', {}).get('peggedUSD') if isinstance(rec.get('circulating'), dict) else ''}"
                items.append(self._item(source, title, content, "https://defillama.com/stablecoins", now, raw=rec))
            return [item for item in items if item["publish_time"] >= window_start]
        if source.name == "GDELT DOC 2.1":
            records = data.get("articles", []) if isinstance(data, dict) else []
            items = []
            for rec in records:
                published = _parse_dt(rec.get("seendate") or rec.get("date"))
                if published < window_start:
                    continue
                title = self._clean(rec.get("title") or "")
                if not title:
                    continue
                items.append(self._item(source, title, rec.get("domain") or rec.get("sourceCountry") or "", rec.get("url") or "", published, raw=rec))
            return items
        return []

    def _json_item(
        self,
        source: PublicSource,
        rec: Dict[str, Any],
        window_start: datetime,
        title_key: str,
        content_key: str,
        date_key: Optional[str],
    ) -> Dict[str, Any]:
        title = self._clean(str(rec.get(title_key) or source.name))
        content = self._clean(str(rec.get(content_key) or ""))
        published = _parse_dt(rec.get(date_key)) if date_key else datetime.utcnow()
        if published < window_start:
            return {}
        url = str(rec.get("url") or rec.get("link") or source.url)
        return self._item(source, title, content, url, published, raw=rec)

    def _parse_html_links(self, source: PublicSource, text: str, window_start: datetime) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(text, "html.parser")
        now = datetime.utcnow()
        items: List[Dict[str, Any]] = []
        keyword_pattern = re.compile("|".join(re.escape(k) for k in [*GLOBAL_KEYWORDS, *MARKET_KEYWORDS]), re.IGNORECASE)
        for anchor in soup.select("a[href]"):
            title = self._clean(anchor.get_text(" ", strip=True))
            if len(title) < 8 or len(title) > 220:
                continue
            href = str(anchor.get("href") or "")
            url = urljoin(source.url, href)
            if not url.startswith("http"):
                continue
            if source.language == "zh" or keyword_pattern.search(title) or source.category in {"macro", "health", "food"}:
                items.append(self._item(source, title, "Public HTML link metadata.", url, now, raw={"href": href}))
            if len(items) >= min(source.max_items, self.max_items_per_source):
                break
        return [item for item in self._dedupe(items) if item["publish_time"] >= window_start]

    async def _robots_allows(self, client: httpx.AsyncClient, url: str) -> bool:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        try:
            response = await client.get(robots_url)
            if response.status_code >= 400:
                return True
            parser = RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(response.text.splitlines())
            return parser.can_fetch(USER_AGENT, url)
        except Exception:
            return True

    def _entry_datetime(self, entry: Dict[str, Any]) -> Optional[datetime]:
        for key in ("published_parsed", "updated_parsed"):
            value = entry.get(key)
            if value:
                return datetime(*value[:6])
        for key in ("published", "updated", "created"):
            raw = entry.get(key)
            if raw:
                try:
                    parsed = parsedate_to_datetime(str(raw))
                    if parsed.tzinfo:
                        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                    return parsed
                except Exception:
                    parsed = _parse_dt(raw)
                    if parsed:
                        return parsed
        return None

    def _item(
        self,
        source: PublicSource,
        title: str,
        content: str,
        url: str,
        published: datetime,
        *,
        raw: Any,
    ) -> Dict[str, Any]:
        text = f"{title} {content}"
        sentiment = _sentiment_score(text)
        return {
            "symbol": None,
            "title": title[:220],
            "content": content[:1200],
            "summary": content[:260],
            "url": url,
            "source": source.name,
            "publish_time": published,
            "category": source.category,
            "sentiment": _sentiment_label(sentiment),
            "sentiment_score": sentiment,
            "importance": "high" if any(k in text for k in GLOBAL_KEYWORDS) else "medium",
            "keywords": self._keywords(text),
            "data_source": f"public_{source.access}",
            "language": source.language,
            "country": source.country,
            "license_note": source.license_note,
            "raw_url": source.url,
            "retrieved_at": datetime.utcnow(),
            "raw_digest": hashlib.sha1(repr(raw).encode("utf-8", errors="ignore")).hexdigest()[:16],
        }

    def _status(
        self,
        source: PublicSource,
        ok: bool,
        count: int,
        message: str,
        latest_publish_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        return {
            "source": f"public:{source.name}",
            "ok": ok,
            "fetched": count,
            "saved": 0,
            "failed": 0 if ok else 1,
            "latest_publish_time": latest_publish_time,
            "message": message,
            "category": source.category,
            "access": source.access,
            "url": source.url,
        }

    def _keywords(self, text: str) -> List[str]:
        matched = [kw for kw in [*GLOBAL_KEYWORDS, *MARKET_KEYWORDS] if kw and kw.lower() in text.lower()]
        return sorted(set(matched))[:12]

    def _clean(self, value: str) -> str:
        value = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
        return re.sub(r"\s+", " ", value).strip()

    def _dedupe(self, items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        result = []
        for item in items:
            if not item:
                continue
            key = (item.get("url") or "", item.get("title") or "", item.get("source") or "")
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result


def get_public_intel_collector() -> PublicIntelCollector:
    return PublicIntelCollector()
