"""Fetch job rows from TopCV listing pages into a DataFrame matching ``extract`` CSV shape.

Parses ``div.job-item-search-result`` cards (2025–2026 layout).  Pagination follows
``a[rel=next]`` using ``data-href`` when present.

Pass ``known_links`` to enable early-stop deduplication: once an entire listing page
contains only known links the crawl stops, since TopCV sorts newest-first.

HTTP reliability: all page fetches go through ``_fetch_with_retry``, which applies
exponential backoff with jitter on transient errors (connection timeouts, 5xx) and
rate-limit responses (429).  Non-retryable 4xx errors (except 429) are re-raised
immediately.
"""

from __future__ import annotations

import logging
import random
import re
import time
from datetime import date
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

from etl.errors import CrawlError

logger = logging.getLogger(__name__)

DEFAULT_LISTING = "https://www.topcv.vn/viec-lam-it?sort=up_top"
USER_AGENT = (
    "Mozilla/5.0 (compatible; basic-etl-pipeline/1.0; +https://github.com/)"
)

_CSV_COLUMNS = [
    "created_date",
    "job_title",
    "company",
    "salary",
    "address",
    "time",
    "link_description",
]


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _canonical_job_url(href: str) -> str:
    """Strip tracking query-string params for a stable, comparable URL."""
    p = urlparse(href)
    return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))


def _fetch_with_retry(
    session: requests.Session,
    url: str,
    *,
    max_retries: int = 3,
    backoff_base: float = 2.0,
    timeout: int = 45,
) -> BeautifulSoup:
    """Fetch *url* with exponential backoff + full jitter on transient failures.

    Args:
        session: Shared ``requests.Session`` (caller manages lifecycle).
        url: Absolute URL to fetch.
        max_retries: Maximum number of retry attempts after the first try.
        backoff_base: Base for exponential backoff (seconds).  Actual wait is
            ``backoff_base ** attempt + uniform(0, 1)`` to avoid thundering herd.
        timeout: Per-request socket timeout in seconds.

    Returns:
        Parsed ``BeautifulSoup`` object.

    Raises:
        CrawlError: All attempts exhausted without a successful response.
        requests.HTTPError: Non-retryable 4xx response (e.g. 403, 404).
    """
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            response = session.get(url, timeout=timeout)

            if response.status_code == 429:
                wait = backoff_base ** attempt + random.uniform(0, 1)
                logger.warning(
                    "Rate-limited (429) on %s. Backing off %.1fs (attempt %d/%d).",
                    url, wait, attempt + 1, max_retries,
                )
                time.sleep(wait)
                last_exc = requests.HTTPError(response=response)
                continue

            response.raise_for_status()
            response.encoding = response.apparent_encoding or "utf-8"
            return BeautifulSoup(response.text, "html.parser")

        except requests.HTTPError as exc:
            # 4xx other than 429 → fail fast, no retry
            if exc.response is not None and exc.response.status_code < 500:
                raise
            last_exc = exc

        except requests.RequestException as exc:
            last_exc = exc

        if attempt < max_retries:
            wait = backoff_base ** attempt + random.uniform(0, 1)
            logger.warning(
                "Fetch failed (%s). Retry %d/%d in %.1fs.",
                last_exc, attempt + 1, max_retries, wait,
            )
            time.sleep(wait)

    raise CrawlError(
        f"Failed to fetch {url} after {max_retries + 1} attempt(s)."
    ) from last_exc


# ── HTML parsing ──────────────────────────────────────────────────────────────

def _text(el: Any) -> str:
    if el is None:
        return ""
    return re.sub(r"\s+", " ", el.get_text(separator=" ", strip=True)).strip()


def _parse_job_card(card: BeautifulSoup) -> dict[str, str] | None:
    """Parse one ``job-item-search-result`` card into a row dict.

    Args:
        card: BeautifulSoup tag for a single job card.

    Returns:
        Dict with keys matching ``_CSV_COLUMNS``, or ``None`` if the card
        cannot be parsed (missing title link, unrecognised URL pattern).
    """
    title_a = card.select_one("h3.title a[href]")
    if not title_a:
        return None

    href = title_a.get("href") or ""
    if not href or ("/viec-lam/" not in href and "/brand/" not in href):
        return None

    title_span = title_a.select_one("span[data-toggle]")
    job_title = _text(title_span if title_span else title_a)

    company    = _text(card.select_one("a.company span.company-name"))
    salary     = _text(
        card.select_one("label.title-salary")
        or card.select_one("label.salary span")
    )
    address    = _text(card.select_one("label.address span.city-text"))
    time_label = _text(
        card.select_one("label.address.mobile-hidden.label-update")
        or card.select_one("label.label-update")
    )

    return {
        "created_date":    date.today().isoformat(),
        "job_title":       job_title,
        "company":         company,
        "salary":          salary,
        "address":         address,
        "time":            time_label,
        "link_description": _canonical_job_url(urljoin("https://www.topcv.vn", href)),
    }


def _next_page_url(soup: BeautifulSoup) -> str | None:
    """Return the URL for the next listing page, or None if none exists."""
    link = soup.find("a", rel="next")
    if not link:
        return None
    nxt = link.get("data-href") or link.get("href")
    if not nxt or nxt in ("#", "javascript:void(0)"):
        return None
    return urljoin("https://www.topcv.vn", nxt)


# ── Public API ────────────────────────────────────────────────────────────────

def crawl_topcv(
    listing_url: str = DEFAULT_LISTING,
    *,
    max_pages: int = 15,
    delay_seconds: float = 2.0,
    max_retries: int = 3,
    backoff_base: float = 2.0,
    session: requests.Session | None = None,
    known_links: set[str] | None = None,
) -> pd.DataFrame:
    """Collect new job rows from TopCV listing pages.

    Args:
        listing_url: First listing page URL (defaults to IT jobs sorted by recency).
        max_pages: Maximum number of pages to paginate through.
        delay_seconds: Polite pause between successive page requests (seconds).
        max_retries: Retry attempts per page on transient HTTP failure.
        backoff_base: Exponential backoff base (seconds) passed to ``_fetch_with_retry``.
        session: Optional shared ``requests.Session``; caller owns its lifecycle.
        known_links: Set of canonical job URLs already in the database.  Cards
            whose link is in this set are skipped.  When an entire page yields
            zero new cards the crawl stops early — subsequent pages are older.

    Returns:
        DataFrame with columns ``["created_date", "job_title", "company",
        "salary", "address", "time", "link_description"]``.
        Contains only rows not present in ``known_links`` (or all rows if
        ``known_links`` is ``None``).

    Raises:
        CrawlError: A page fetch failed after all retries.
    """
    own_session = session is None
    sess = session or requests.Session()
    sess.headers.setdefault("User-Agent", USER_AGENT)

    rows: list[dict[str, str]] = []
    page_url: str | None = listing_url
    pages_done = 0

    try:
        while page_url and pages_done < max_pages:
            logger.info("Crawling page %d/%d — %s", pages_done + 1, max_pages, page_url)

            soup = _fetch_with_retry(
                sess, page_url,
                max_retries=max_retries,
                backoff_base=backoff_base,
            )
            cards = soup.select("div.job-item-search-result")

            new_on_page = 0
            for card in cards:
                row = _parse_job_card(card)
                if not row:
                    continue
                if known_links is not None and row["link_description"] in known_links:
                    continue
                rows.append(row)
                new_on_page += 1

            pages_done += 1

            if known_links is not None and new_on_page == 0 and cards:
                logger.info(
                    "Page %d: all %d cards already known — stopping early.",
                    pages_done, len(cards),
                )
                break

            page_url = _next_page_url(soup)
            if page_url and pages_done < max_pages and delay_seconds > 0:
                time.sleep(delay_seconds)

    finally:
        if own_session:
            sess.close()

    if not rows:
        logger.warning("No job rows parsed — TopCV HTML selectors may need updating.")

    return pd.DataFrame(rows, columns=_CSV_COLUMNS)
