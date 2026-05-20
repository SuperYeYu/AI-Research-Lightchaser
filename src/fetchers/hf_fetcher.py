from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.models import HuggingFaceItem

HF_DAILY_PAPERS_URL = "https://huggingface.co/papers"
HF_WEEKLY_PAPERS_URL = "https://huggingface.co/papers/trending"


def build_hf_papers_url(period: str) -> str:
    return HF_WEEKLY_PAPERS_URL if str(period).strip().lower() == "weekly" else HF_DAILY_PAPERS_URL


def extract_hf_detail_summary(html: str, max_chars: int = 2400) -> str:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)

    def extract_between(start_marker: str, end_markers: list[str]) -> str:
        lowered = text.lower()
        start_index = lowered.find(start_marker.lower())
        if start_index < 0:
            return ""
        start_index += len(start_marker)
        end_index = len(text)
        for marker in end_markers:
            marker_index = lowered.find(marker.lower(), start_index)
            if marker_index >= 0:
                end_index = min(end_index, marker_index)
        value = re.sub(r"\s+", " ", text[start_index:end_index]).strip()
        return value[:max_chars].strip()

    ai_summary = extract_between("AI-generated summary", ["Abstract", "Community", "Models citing this paper"])
    if ai_summary:
        return ai_summary
    abstract = extract_between("Abstract", ["Community", "Models citing this paper", "References"])
    if abstract:
        return abstract
    return ""


def parse_hf_daily_papers_html(html: str) -> list[HuggingFaceItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[HuggingFaceItem] = []
    seen_urls: set[str] = set()
    for anchor in soup.select('a[href^="/papers/"]'):
        title = anchor.get_text(" ", strip=True)
        href = anchor.get("href", "")
        if not title or not href:
            continue
        if "#" in href:
            continue
        url = urljoin("https://huggingface.co", href)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        container = anchor.find_parent(["article", "div", "section", "li"]) or anchor.parent
        summary_node = None
        if container is not None:
            summary_node = container.find("p")
        summary = summary_node.get_text(" ", strip=True) if summary_node else ""
        arxiv_url = None
        if container is not None:
            arxiv_anchor = container.find("a", href=lambda value: isinstance(value, str) and "arxiv.org" in value)
            if arxiv_anchor is not None:
                arxiv_url = arxiv_anchor.get("href")
        items.append(
            HuggingFaceItem(
                source="huggingface",
                id=url,
                title=title,
                url=url,
                summary=summary,
                authors=[],
                published_at=None,
                meta={},
                paper_page_url=url,
                arxiv_url=arxiv_url,
                hf_summary=summary,
            )
        )
    return items


def fetch_hf_detail_summary(session: requests.Session, paper_url: str) -> str:
    response = session.get(paper_url, timeout=30)
    response.raise_for_status()
    return extract_hf_detail_summary(response.text)


def fetch_hf_daily_papers(session: requests.Session, period: str = "daily") -> list[HuggingFaceItem]:
    response = session.get(build_hf_papers_url(period), timeout=30)
    response.raise_for_status()
    return parse_hf_daily_papers_html(response.text)
