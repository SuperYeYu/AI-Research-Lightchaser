from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

from src.models import ArxivItem, GithubItem, HuggingFaceItem, ProfileConfig


class DeepSeekError(RuntimeError):
    pass


class DeepSeekClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int = 60,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "").strip()
        self.base_url = (base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")).rstrip("/")
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        self.timeout = timeout
        self.session = session or requests.Session()

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _extract_json(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DeepSeekError(f"invalid JSON response: {content}") from exc
        if not isinstance(parsed, dict):
            raise DeepSeekError("DeepSeek response JSON must be an object")
        return parsed

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        if not self.enabled:
            raise DeepSeekError("DEEPSEEK_API_KEY is missing")
        response = self.session.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        content = (((payload.get("choices") or [{}])[0]).get("message") or {}).get("content", "")
        return self._extract_json(content)

    def summary_needs_retry(self, summary: str) -> bool:
        text = re.sub(r"\s+", " ", summary or "").strip()
        sentence_count = len([part for part in re.split(r"[。！？!?]", text) if part.strip()])
        if sentence_count >= 3:
            return False
        if len(text) < 30:
            return True
        return sentence_count < 2

    def rerank_arxiv(self, profile: ProfileConfig, item: ArxivItem) -> tuple[int, str, str]:
        result = self.chat_json(
            system_prompt=(
                "You are a research relevance evaluator. Only use the given field description, title, and abstract. "
                "Return JSON with score, verdict, reason_zh."
            ),
            user_prompt=(
                f"Field name: {profile.name}\n"
                f"Field description: {profile.description}\n"
                f"Keywords: {', '.join(profile.keywords)}\n"
                f"Queries: {'; '.join(profile.queries)}\n"
                f"Paper title: {item.title}\n"
                f"Paper abstract: {item.abstract}\n"
                "Return JSON. score is 0-100 integer. verdict is one of highly_relevant/relevant/weakly_relevant/irrelevant. "
                "reason_zh is one concise Chinese sentence."
            ),
        )
        return int(result["score"]), str(result["verdict"]), str(result["reason_zh"])

    def summarize_arxiv(self, item: ArxivItem, profile_name: str) -> tuple[str, str]:
        result = self.chat_json(
            system_prompt=(
                "You are a Chinese research editor. Translate or condense the paper abstract into fluent Chinese in 4-5 sentences. "
                "Return JSON only with summary_zh."
            ),
            user_prompt=(
                f"Field: {profile_name}\n"
                f"Title: {item.title}\n"
                f"Abstract: {item.abstract}\n"
                'Return JSON: {"summary_zh": "..."}'
            ),
        )
        return str(result["summary_zh"]), ""

    def summarize_github(self, item: GithubItem) -> tuple[str, str]:
        system_prompt = (
            "You are a Chinese technical editor. Explain what the project does and why it is worth attention in 4-5 Chinese sentences. "
            "Return JSON only with summary_zh."
        )
        user_prompt = (
            f"Project: {item.repo_name}\n"
            f"Description: {item.description}\n"
            f"Language: {item.language}\n"
            f"Today stars: {item.stars_today}\n"
            f"Total stars: {item.stars_total}\n"
            f"README excerpt: {item.readme_excerpt}\n"
            'Return JSON: {"summary_zh": "..."}'
        )
        result = self.chat_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        summary = str(result["summary_zh"])
        if self.summary_needs_retry(summary):
            result = self.chat_json(
                system_prompt=(
                    "You are a Chinese technical editor. Write a richer 4-5 sentence summary. "
                    "You must cover project positioning, main capabilities, likely users or usage scene, and why it is worth attention. "
                    "Do not return a one-sentence answer. Return JSON only with summary_zh."
                ),
                user_prompt=user_prompt,
            )
            summary = str(result["summary_zh"])
        return summary, ""

    def summarize_hf(self, item: HuggingFaceItem) -> tuple[str, str]:
        result = self.chat_json(
            system_prompt=(
                "You are a Chinese research editor. Translate or condense the paper abstract into fluent Chinese in 4-5 sentences. "
                "Return JSON only with summary_zh."
            ),
            user_prompt=(
                f"Title: {item.title}\n"
                f"Summary or abstract: {item.detail_summary or item.hf_summary or item.summary}\n"
                'Return JSON: {"summary_zh": "..."}'
            ),
        )
        return str(result["summary_zh"]), ""
