from __future__ import annotations

import os
from pathlib import Path

import yaml

from src.models import AppConfig, ProfileConfig, ReportSettings


def load_dotenv_file(path: Path, override: bool = False) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and (override or key not in os.environ):
            os.environ[key] = value


def _ensure_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{field_name} must be a non-empty list of strings")
    return [item.strip() for item in value]


def _parse_profiles(raw_profiles: object) -> list[ProfileConfig]:
    if not isinstance(raw_profiles, list) or not raw_profiles:
        raise ValueError("profiles must be a non-empty list")
    profiles: list[ProfileConfig] = []
    seen_ids: set[str] = set()
    for raw_profile in raw_profiles:
        if not isinstance(raw_profile, dict):
            raise ValueError("profile must be an object")
        profile_id = str(raw_profile.get("id", "")).strip()
        if not profile_id:
            raise ValueError("profile.id is required")
        if profile_id in seen_ids:
            raise ValueError(f"duplicate profile id: {profile_id}")
        seen_ids.add(profile_id)
        name = str(raw_profile.get("name", "")).strip()
        description = str(raw_profile.get("description", "")).strip()
        if not name or not description:
            raise ValueError(f"profile {profile_id} must include name and description")
        profiles.append(
            ProfileConfig(
                id=profile_id,
                name=name,
                description=description,
                keywords=_ensure_list(raw_profile.get("keywords"), f"profile {profile_id}.keywords"),
                queries=_ensure_list(raw_profile.get("queries"), f"profile {profile_id}.queries"),
            )
        )
    return profiles


def _parse_report(raw_report: object) -> ReportSettings:
    raw_report = raw_report if isinstance(raw_report, dict) else {}
    return ReportSettings(
        timezone=str(raw_report.get("timezone", "Asia/Shanghai")).strip() or "Asia/Shanghai",
        lookback_hours=int(raw_report.get("lookback_hours", 24)),
        max_arxiv_fetch_results_per_profile=int(raw_report.get("max_arxiv_fetch_results_per_profile", 200)),
        max_arxiv_candidates_per_profile=int(raw_report.get("max_arxiv_candidates_per_profile", 100)),
        max_arxiv_results_per_profile=int(raw_report.get("max_arxiv_results_per_profile", 20)),
        max_github_results=int(raw_report.get("max_github_results", 15)),
        max_hf_results=int(raw_report.get("max_hf_results", 15)),
    )


def parse_mail_to(env: dict[str, str] | None = None) -> list[str]:
    env = env or os.environ
    raw = env.get("MAIL_TO", "")
    return [address.strip() for address in raw.split(",") if address.strip()]


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("config root must be a mapping")
    return AppConfig(
        report=_parse_report(data.get("report")),
        profiles=_parse_profiles(data.get("profiles")),
        mail_to=parse_mail_to(),
    )
