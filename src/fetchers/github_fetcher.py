from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.models import GithubItem

GITHUB_TRENDING_URL = "https://github.com/trending"


def _normalize_repo_name(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _parse_number(text: str) -> int:
    match = re.search(r"(\d[\d,]*)", text or "")
    return int(match.group(1).replace(",", "")) if match else 0


def _parse_stars_today(text: str) -> int:
    normalized = re.sub(r"\s+", " ", text or "").strip().lower()
    match = re.search(r"(\d[\d,]*)\s+stars today$", normalized)
    return int(match.group(1).replace(",", "")) if match else 0


def build_github_trending_url(period: str) -> str:
    since = "weekly" if str(period).strip().lower() == "weekly" else "daily"
    return f"{GITHUB_TRENDING_URL}?since={since}"


def extract_readme_excerpt(text: str, max_chars: int = 2400) -> str:
    value = re.sub(r"```[\s\S]*?```", " ", text or "")
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"^#+\s*", "", value, flags=re.M)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


def parse_github_trending_html(html: str) -> list[GithubItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[GithubItem] = []
    for article in soup.select("article.Box-row"):
        repo_anchor = article.select_one("h2 a")
        if repo_anchor is None:
            continue
        repo_name = _normalize_repo_name(repo_anchor.get_text(" ", strip=True))
        repo_url = urljoin("https://github.com", repo_anchor.get("href", ""))
        description_node = article.select_one("p")
        language_node = article.select_one('[itemprop="programmingLanguage"]')
        stars_today = 0
        for candidate in article.find_all(["span", "div"]):
            text = candidate.get_text(" ", strip=True)
            if "stars today" in text.lower():
                parsed = _parse_stars_today(text)
                if parsed:
                    stars_today = parsed
                    break
        total_stars = 0
        for anchor in article.find_all("a", href=True):
            if anchor["href"].endswith("/stargazers"):
                total_stars = _parse_number(anchor.get_text(" ", strip=True))
                break
        description = description_node.get_text(" ", strip=True) if description_node else ""
        language = language_node.get_text(" ", strip=True) if language_node else ""
        items.append(
            GithubItem(
                source="github",
                id=repo_name,
                title=repo_name,
                url=repo_url,
                summary=description,
                authors=[],
                published_at=None,
                meta={},
                repo_name=repo_name,
                description=description,
                language=language,
                stars_today=stars_today,
                stars_total=total_stars,
            )
        )
    return items


def fetch_github_readme_excerpt(session: requests.Session, repo_name: str) -> str:
    api_url = f"https://api.github.com/repos/{repo_name}/readme"
    response = session.get(
        api_url,
        headers={
            "Accept": "application/vnd.github.raw",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30,
    )
    response.raise_for_status()
    return extract_readme_excerpt(response.text)


def fetch_github_trending(session: requests.Session, period: str = "daily") -> list[GithubItem]:
    response = session.get(build_github_trending_url(period), timeout=30)
    response.raise_for_status()
    return parse_github_trending_html(response.text)
