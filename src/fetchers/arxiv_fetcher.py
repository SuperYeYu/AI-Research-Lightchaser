from __future__ import annotations

import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from xml.etree import ElementTree as ET

from src.models import ArxivItem, ProfileConfig

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
DEFAULT_CATEGORIES = ["cs.AI", "cs.CL", "cs.LG", "cs.MA", "cs.SI"]


def _extract_arxiv_id(raw_id: str) -> str:
    return raw_id.rstrip("/").split("/")[-1]


def parse_arxiv_atom(xml_text: str, now: datetime, lookback_hours: int) -> list[ArxivItem]:
    root = ET.fromstring(xml_text)
    cutoff = now.astimezone(UTC) - timedelta(hours=lookback_hours)
    items: list[ArxivItem] = []
    for entry in root.findall("atom:entry", ATOM_NS):
        published_text = entry.findtext("atom:published", default="", namespaces=ATOM_NS)
        if not published_text:
            continue
        published_at = datetime.strptime(published_text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        if published_at < cutoff:
            continue
        raw_id = entry.findtext("atom:id", default="", namespaces=ATOM_NS).strip()
        title = " ".join(entry.findtext("atom:title", default="", namespaces=ATOM_NS).split())
        abstract = " ".join(entry.findtext("atom:summary", default="", namespaces=ATOM_NS).split())
        authors = [
            " ".join((author.findtext("atom:name", default="", namespaces=ATOM_NS) or "").split())
            for author in entry.findall("atom:author", ATOM_NS)
            if (author.findtext("atom:name", default="", namespaces=ATOM_NS) or "").strip()
        ]
        categories = [category.attrib.get("term", "").strip() for category in entry.findall("atom:category", ATOM_NS)]
        arxiv_id = _extract_arxiv_id(raw_id)
        items.append(
            ArxivItem(
                source="arxiv",
                id=arxiv_id,
                title=title,
                url=raw_id,
                summary=abstract,
                authors=authors,
                published_at=published_at,
                meta={},
                arxiv_id=arxiv_id,
                abstract=abstract,
                categories=[category for category in categories if category],
            )
        )
    items.sort(key=lambda item: item.published_at or datetime.min.replace(tzinfo=UTC), reverse=True)
    return items


def build_arxiv_query(categories: list[str] | None = None) -> str:
    categories = categories or DEFAULT_CATEGORIES
    return " OR ".join(f"cat:{category}" for category in categories)


def _keyword_clause(keyword: str) -> str:
    cleaned = keyword.strip()
    if not cleaned:
        return ""
    if " " in cleaned or "-" in cleaned:
        quoted = f'"{cleaned}"'
        return f"ti:{quoted} OR abs:{quoted}"
    return f"ti:{cleaned} OR abs:{cleaned}"


def build_profile_arxiv_query(profile: ProfileConfig) -> str:
    clauses = [_keyword_clause(keyword) for keyword in profile.keywords]
    clauses = [clause for clause in clauses if clause]
    if not clauses:
        return build_arxiv_query()
    return "(" + " OR ".join(clauses) + ")"


def fetch_arxiv_candidates(
    session,
    now: datetime,
    lookback_hours: int,
    max_results: int = 200,
    categories: list[str] | None = None,
    search_query: str | None = None,
    max_retries: int = 3,
    sleep_fn=time.sleep,
    urlopen_fn=urllib.request.urlopen,
) -> list[ArxivItem]:
    params = {
        "search_query": search_query or build_arxiv_query(categories),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": str(max_results),
    }
    url = f"{ARXIV_API_URL}?{urllib.parse.urlencode(params)}"
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "arxiv-digest-bot"})
            with urlopen_fn(request, timeout=30) as response:
                payload = response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            last_error = exc
            if attempt < max_retries:
                sleep_fn(float(2 ** (attempt - 1)))
                continue
            raise
        return parse_arxiv_atom(payload, now=now, lookback_hours=lookback_hours)
    if last_error is not None:
        raise last_error
    raise RuntimeError("arXiv fetch failed without response")
