from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class ProfileConfig:
    id: str
    name: str
    description: str
    keywords: list[str]
    queries: list[str]


@dataclass(slots=True)
class ReportSettings:
    timezone: str = "Asia/Shanghai"
    lookback_hours: int = 24
    max_arxiv_fetch_results_per_profile: int = 200
    max_arxiv_candidates_per_profile: int = 100
    max_arxiv_results_per_profile: int = 20
    max_github_results: int = 15
    max_hf_results: int = 15


@dataclass(slots=True)
class AppConfig:
    report: ReportSettings
    profiles: list[ProfileConfig]
    mail_to: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ArxivProfileScore:
    rule_score: float
    normalized_rule_score: float
    llm_score: int
    final_score: float
    verdict: str
    reason_zh: str


@dataclass(slots=True)
class SourceItem:
    source: str
    id: str
    title: str
    url: str
    summary: str
    authors: list[str]
    published_at: datetime | None
    meta: dict[str, Any] = field(default_factory=dict)
    summary_zh: str = ""
    core_idea_zh: str = ""


@dataclass(slots=True)
class ArxivItem(SourceItem):
    arxiv_id: str = ""
    abstract: str = ""
    categories: list[str] = field(default_factory=list)
    profile_scores: dict[str, ArxivProfileScore] = field(default_factory=dict)


@dataclass(slots=True)
class GithubItem(SourceItem):
    repo_name: str = ""
    description: str = ""
    language: str = ""
    stars_today: int = 0
    stars_total: int = 0
    readme_excerpt: str = ""


@dataclass(slots=True)
class HuggingFaceItem(SourceItem):
    paper_page_url: str = ""
    arxiv_url: str | None = None
    hf_summary: str = ""
    detail_summary: str = ""


@dataclass(slots=True)
class RenderedReport:
    generated_at: datetime
    lookback_hours: int
    arxiv_sections: dict[str, list[ArxivItem]]
    github_items: list[GithubItem]
    hf_items: list[HuggingFaceItem]
    html: str
    period: str = "daily"
