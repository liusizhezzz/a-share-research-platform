"""
News freshness helpers shared by analyst-facing news tools.

The upstream sources can return mixed and loosely sorted results, so every
analysis path must parse publish times and drop stale items before prompting an
LLM.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import Any, Iterable, List, Optional, Sequence, Tuple


DEFAULT_MAX_AGE_DAYS = 7
DEFAULT_FUTURE_TOLERANCE_DAYS = 1


def get_news_max_age_days(default: int = DEFAULT_MAX_AGE_DAYS) -> int:
    """Return the configured freshness window for stock-analysis news."""
    raw = os.getenv("ANALYSIS_NEWS_MAX_AGE_DAYS", "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
        return value if value > 0 else default
    except ValueError:
        return default


def parse_news_datetime(value: Any, now: Optional[datetime] = None) -> Optional[datetime]:
    """Parse common Chinese financial-news time formats into a naive datetime."""
    now = now or datetime.now()
    if value is None:
        return None

    if isinstance(value, datetime):
        if value.tzinfo:
            return value.astimezone().replace(tzinfo=None)
        return value

    if hasattr(value, "to_pydatetime"):
        try:
            parsed = value.to_pydatetime()
            return parsed.replace(tzinfo=None) if getattr(parsed, "tzinfo", None) else parsed
        except Exception:
            pass

    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000
        try:
            return datetime.fromtimestamp(timestamp)
        except Exception:
            return None

    text = re.sub(r"<[^>]+>", "", str(value)).strip()
    if not text or text.lower() in {"nan", "none", "null", "-"}:
        return None

    text = (
        text.replace("年", "-")
        .replace("月", "-")
        .replace("日", "")
        .replace("/", "-")
        .replace("T", " ")
    )
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(发布于|发表于|更新时间[:：]?|时间[:：]?)", "", text).strip()
    text = re.sub(r"\.\d+(Z)?$", "", text)
    text = re.sub(r"([+-]\d{2}:?\d{2}|Z)$", "", text).strip()

    relative_patterns = [
        (r"(\d+)\s*分钟前", "minutes"),
        (r"(\d+)\s*小时前", "hours"),
        (r"(\d+)\s*天前", "days"),
    ]
    if text in {"刚刚", "刚才"}:
        return now
    for pattern, unit in relative_patterns:
        match = re.search(pattern, text)
        if match:
            amount = int(match.group(1))
            return now - timedelta(**{unit: amount})

    for prefix, days in (("今天", 0), ("昨日", 1), ("昨天", 1), ("前天", 2)):
        if text.startswith(prefix):
            rest = text[len(prefix):].strip()
            base = now - timedelta(days=days)
            if re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", rest):
                parts = [int(part) for part in rest.split(":")]
                return base.replace(
                    hour=parts[0],
                    minute=parts[1],
                    second=parts[2] if len(parts) > 2 else 0,
                    microsecond=0,
                )
            return base.replace(hour=0, minute=0, second=0, microsecond=0)

    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y%m%d %H:%M:%S",
        "%Y%m%d %H:%M",
        "%Y%m%d",
        "%m-%d %H:%M:%S",
        "%m-%d %H:%M",
        "%m-%d",
        "%H:%M:%S",
        "%H:%M",
    )
    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt)
            if "%Y" not in fmt:
                parsed = parsed.replace(year=now.year)
                if parsed > now + timedelta(days=DEFAULT_FUTURE_TOLERANCE_DAYS):
                    parsed = parsed.replace(year=parsed.year - 1)
            if fmt in {"%H:%M:%S", "%H:%M"}:
                parsed = now.replace(
                    hour=parsed.hour,
                    minute=parsed.minute,
                    second=parsed.second,
                    microsecond=0,
                )
            return parsed
        except ValueError:
            continue

    match = re.search(r"(\d{4}-\d{1,2}-\d{1,2})(?:\s+(\d{1,2}:\d{2}(?::\d{2})?))?", text)
    if match:
        candidate = f"{match.group(1)} {match.group(2) or '00:00:00'}"
        return parse_news_datetime(candidate, now=now)

    return None


def is_recent_news_time(
    value: Any,
    *,
    max_age_days: Optional[int] = None,
    now: Optional[datetime] = None,
) -> bool:
    """Return True only when a publish time sits inside the accepted window."""
    now = now or datetime.now()
    max_age_days = max_age_days or get_news_max_age_days()
    parsed = parse_news_datetime(value, now=now)
    if not parsed:
        return False
    return now - timedelta(days=max_age_days) <= parsed <= now + timedelta(days=DEFAULT_FUTURE_TOLERANCE_DAYS)


def freshness_window(max_age_days: Optional[int] = None, now: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    now = now or datetime.now()
    max_age_days = max_age_days or get_news_max_age_days()
    return now - timedelta(days=max_age_days), now + timedelta(days=DEFAULT_FUTURE_TOLERANCE_DAYS)


def filter_recent_items(
    items: Iterable[dict],
    *,
    time_keys: Sequence[str] = ("publish_time", "发布时间", "时间", "date", "showTime", "time"),
    max_age_days: Optional[int] = None,
    limit: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Tuple[List[dict], int]:
    """Filter dict news items by freshness and sort newest first."""
    now = now or datetime.now()
    max_age_days = max_age_days or get_news_max_age_days()
    recent: List[Tuple[datetime, dict]] = []
    stale_or_unknown = 0

    for item in items:
        published = None
        for key in time_keys:
            if key in item and item.get(key) not in (None, ""):
                published = parse_news_datetime(item.get(key), now=now)
                if published:
                    break

        if published and is_recent_news_time(published, max_age_days=max_age_days, now=now):
            normalized = dict(item)
            normalized["publish_time"] = published
            recent.append((published, normalized))
        else:
            stale_or_unknown += 1

    recent.sort(key=lambda pair: pair[0], reverse=True)
    filtered = [item for _, item in recent]
    if limit is not None:
        filtered = filtered[:limit]
    return filtered, stale_or_unknown


def filter_recent_dataframe(
    df: Any,
    *,
    time_columns: Sequence[str] = ("发布时间", "时间", "publish_time", "date", "showTime"),
    max_age_days: Optional[int] = None,
    limit: Optional[int] = None,
    now: Optional[datetime] = None,
) -> Tuple[Any, int]:
    """Filter a pandas DataFrame by freshness while preserving its columns."""
    if df is None or getattr(df, "empty", True):
        return df, 0

    now = now or datetime.now()
    max_age_days = max_age_days or get_news_max_age_days()
    rows: List[Tuple[datetime, Any]] = []
    stale_or_unknown = 0

    for idx, row in df.iterrows():
        published = None
        for column in time_columns:
            if column in df.columns:
                published = parse_news_datetime(row.get(column), now=now)
                if published:
                    break
        if published and is_recent_news_time(published, max_age_days=max_age_days, now=now):
            rows.append((published, idx))
        else:
            stale_or_unknown += 1

    rows.sort(key=lambda pair: pair[0], reverse=True)
    indices = [idx for _, idx in rows]
    if limit is not None:
        indices = indices[:limit]

    filtered = df.loc[indices].copy()
    return filtered, stale_or_unknown


def format_freshness_line(items: Sequence[dict], *, max_age_days: Optional[int] = None) -> str:
    """Build a compact metadata line for LLM prompts and reports."""
    max_age_days = max_age_days or get_news_max_age_days()
    publish_times = [
        parse_news_datetime(item.get("publish_time"))
        for item in items
        if item.get("publish_time") is not None
    ]
    publish_times = [item for item in publish_times if item is not None]
    if not publish_times:
        return f"数据新鲜度: 已启用最近 {max_age_days} 天过滤，未识别到发布时间"
    latest = max(publish_times).strftime("%Y-%m-%d %H:%M")
    oldest = min(publish_times).strftime("%Y-%m-%d %H:%M")
    return f"数据新鲜度: 仅展示最近 {max_age_days} 天数据，最新 {latest}，最早 {oldest}"
