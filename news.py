# -*- coding: utf-8 -*-
"""
news.py

Очень простой модуль для новостного фона:
- тянем RSS
- фильтруем по ключевым словам
- считаем "тональность" по словарю +/-

Это не торговый сигнал, а контекст.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional

import requests  # already in requirements


@dataclass(frozen=True)
class NewsItem:
    title: str
    published_ms: int
    source: str
    url: str


@dataclass(frozen=True)
class NewsSnapshot:
    score: int
    label: str
    scope: str  # "AVAX" | "MACRO" | "NONE"
    items: List[NewsItem]


def _now_ms() -> int:
    return int(time.time() * 1000)


def _parse_pubdate(s: str) -> Optional[int]:
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def _text_score(text: str, pos: List[str], neg: List[str]) -> int:
    t = (text or "").lower()
    score = 0
    for w in pos:
        if w.lower() in t:
            score += 1
    for w in neg:
        if w.lower() in t:
            score -= 1
    return score


def fetch_rss(url: str, *, timeout: int = 10) -> List[NewsItem]:
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "elliott-bot/1.0"})
        r.raise_for_status()
        root = ET.fromstring(r.text)
        items: List[NewsItem] = []

        # RSS: /rss/channel/item
        for it in root.findall(".//item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            pub = (it.findtext("pubDate") or "").strip()
            pub_ms = _parse_pubdate(pub) or _now_ms()
            items.append(NewsItem(title=title, published_ms=pub_ms, source=url, url=link))
        return items
    except Exception:
        return []


def build_snapshot(
    *,
    rss_urls: List[str],
    lookback_hours: int,
    max_items: int,
    timeout: int,
    strict_keywords: List[str],
    fallback_keywords: List[str],
    pos_keywords: List[str],
    neg_keywords: List[str],
) -> NewsSnapshot:
    now = _now_ms()
    cutoff = now - int(lookback_hours * 3600 * 1000)

    all_items: List[NewsItem] = []
    for u in rss_urls:
        all_items.extend(fetch_rss(u, timeout=timeout))

    # Filter by time + keywords (2-pass):
    # 1) strict (AVAX/AVALANCHE)
    # 2) fallback (BTC/ETH/macro) if strict empty
    strict_kw = [k.lower() for k in (strict_keywords or [])]
    fallback_kw = [k.lower() for k in (fallback_keywords or [])]

    strict_items: List[NewsItem] = []
    fallback_items: List[NewsItem] = []
    for it in all_items:
        if it.published_ms < cutoff:
            continue
        text = it.title.lower()
        if strict_kw and any(k in text for k in strict_kw):
            strict_items.append(it)
            continue
        if fallback_kw and any(k in text for k in fallback_kw):
            fallback_items.append(it)

    filtered = strict_items if strict_items else fallback_items
    scope = "AVAX" if strict_items else ("MACRO" if fallback_items else "NONE")
    filtered.sort(key=lambda x: x.published_ms, reverse=True)
    filtered = filtered[:max_items]

    score = 0
    for it in filtered:
        score += _text_score(it.title, pos_keywords or [], neg_keywords or [])

    if score >= 2:
        label = "позитивный"
    elif score <= -2:
        label = "негативный"
    else:
        label = "нейтральный"

    return NewsSnapshot(score=score, label=label, scope=scope, items=filtered)


