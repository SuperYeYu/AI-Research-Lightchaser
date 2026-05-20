from __future__ import annotations

import re
from datetime import UTC, datetime

from src.models import ArxivItem, ArxivProfileScore, ProfileConfig


def keyword_in_text(keyword: str, text: str) -> bool:
    keyword = keyword.lower().strip()
    text = text.lower()
    if not keyword:
        return False
    if re.fullmatch(r"[a-z0-9+.-]{1,4}", keyword):
        return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text) is not None
    return keyword in text


def compute_recency_bonus(published_at: datetime | None, now: datetime, lookback_hours: int = 24) -> float:
    if published_at is None:
        return 0.0
    age_hours = max(0.0, (now.astimezone(UTC) - published_at.astimezone(UTC)).total_seconds() / 3600)
    if age_hours >= lookback_hours:
        return 0.0
    return max(0.0, 2.0 * (1.0 - age_hours / lookback_hours))


def score_arxiv_item(item: ArxivItem, profile: ProfileConfig, now: datetime, lookback_hours: int = 24) -> float:
    title = item.title.lower()
    abstract = item.abstract.lower()
    categories = " ".join(item.categories).lower()
    score = 0.0
    for keyword in profile.keywords:
        normalized = keyword.lower()
        if keyword_in_text(normalized, title):
            score += 4
        elif keyword_in_text(normalized, abstract):
            score += 2
    query_text = " ".join(profile.queries)
    if query_text.strip():
        for query in profile.queries:
            if keyword_in_text(query.lower(), f"{title} {abstract}"):
                score += 3
    if any(category.startswith("cs.") for category in item.categories) or "stat.ml" in categories:
        score += 1
    score += compute_recency_bonus(item.published_at, now=now, lookback_hours=lookback_hours)
    return score


def normalize_rule_scores(scores: list[float]) -> list[float]:
    if not scores:
        return []
    min_score = min(scores)
    max_score = max(scores)
    if max_score == min_score:
        return [100.0 if max_score > 0 else 0.0 for _ in scores]
    return [((score - min_score) / (max_score - min_score)) * 100.0 for score in scores]


def rank_arxiv_for_profile(
    items: list[ArxivItem],
    profile: ProfileConfig,
    max_candidates: int,
    now: datetime,
    lookback_hours: int = 24,
) -> list[ArxivItem]:
    scored: list[tuple[ArxivItem, float]] = []
    for item in items:
        rule_score = score_arxiv_item(item, profile, now=now, lookback_hours=lookback_hours)
        if rule_score <= 0:
            continue
        scored.append((item, rule_score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    candidates = scored[:max_candidates]
    normalized_scores = normalize_rule_scores([score for _, score in candidates])
    ranked_items: list[ArxivItem] = []
    for (item, rule_score), normalized_score in zip(candidates, normalized_scores, strict=False):
        item.profile_scores[profile.id] = ArxivProfileScore(
            rule_score=rule_score,
            normalized_rule_score=normalized_score,
            llm_score=0,
            final_score=normalized_score,
            verdict="",
            reason_zh="",
        )
        ranked_items.append(item)
    return ranked_items


def apply_llm_rerank(
    item: ArxivItem,
    profile_id: str,
    llm_score: int,
    verdict: str,
    reason_zh: str,
) -> None:
    profile_score = item.profile_scores[profile_id]
    final_score = 0.35 * profile_score.normalized_rule_score + 0.65 * llm_score
    item.profile_scores[profile_id] = ArxivProfileScore(
        rule_score=profile_score.rule_score,
        normalized_rule_score=profile_score.normalized_rule_score,
        llm_score=llm_score,
        final_score=final_score,
        verdict=verdict,
        reason_zh=reason_zh,
    )
