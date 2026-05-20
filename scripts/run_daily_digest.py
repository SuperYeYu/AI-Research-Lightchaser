from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config_loader import load_config, load_dotenv_file
from src.email_sender import send_html_email
from src.fetchers.arxiv_fetcher import build_profile_arxiv_query, fetch_arxiv_candidates
from src.fetchers.github_fetcher import fetch_github_readme_excerpt, fetch_github_trending
from src.fetchers.hf_fetcher import fetch_hf_daily_papers, fetch_hf_detail_summary
from src.models import ArxivItem, GithubItem, HuggingFaceItem, RenderedReport
from src.renderers.email_renderer import render_email_html
from src.scoring.arxiv_rule_ranker import apply_llm_rerank, rank_arxiv_for_profile
from src.storage.seen_store import SeenStore
from src.summarizers.deepseek_client import DeepSeekClient


def log(message: str) -> None:
    print(f"[{datetime.now(tz=UTC).isoformat()}] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run AI research daily digest")
    parser.add_argument("--dry-run", action="store_true", help="render output without sending email")
    parser.add_argument("--skip-send", action="store_true", help="skip SMTP sending")
    parser.add_argument("--now", type=str, default="", help="override current time in ISO format")
    parser.add_argument("--env-file", type=str, default="", help="load an extra env file for tokens and SMTP secrets")
    parser.add_argument("--period", choices=["daily", "weekly"], default="daily", help="digest period")
    return parser.parse_args()


def resolve_now(value: str) -> datetime:
    if not value:
        return datetime.now(tz=UTC)
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def resolve_lookback_hours(period: str, base_hours: int) -> int:
    return base_hours * 7 if period == "weekly" else base_hours


def fallback_text(text: str, limit: int = 220) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def canonical_id_for_hf(item: HuggingFaceItem) -> str:
    return item.arxiv_url or item.paper_page_url or item.url


def source_uses_seen_cache(source: str) -> bool:
    return False


def filter_items_for_digest(items, source: str, key_fn, store: SeenStore, now: datetime, window_hours: int):
    if not source_uses_seen_cache(source):
        return list(items)
    return [item for item in items if not store.should_skip(source, key_fn(item), now=now, window_hours=window_hours)]


def mark_sent_for_digest(store: SeenStore, source: str, items, key_fn, sent_at: datetime) -> None:
    if not source_uses_seen_cache(source):
        return
    for item in items:
        store.mark_sent(source, key_fn(item), sent_at)


def enrich_github_items(session: requests.Session, github_items: Iterable[GithubItem]) -> None:
    for item in github_items:
        try:
            item.readme_excerpt = fetch_github_readme_excerpt(session, item.repo_name)
        except Exception:
            item.readme_excerpt = ""


def enrich_hf_items(session: requests.Session, hf_items: Iterable[HuggingFaceItem]) -> None:
    for item in hf_items:
        try:
            item.detail_summary = fetch_hf_detail_summary(session, item.url)
        except Exception:
            item.detail_summary = ""


def summarize_items(client: DeepSeekClient, github_items: Iterable[GithubItem], hf_items: Iterable[HuggingFaceItem]) -> None:
    for item in github_items:
        try:
            item.summary_zh, item.core_idea_zh = client.summarize_github(item)
        except Exception:
            item.summary_zh = fallback_text(item.readme_excerpt or item.description or item.summary)
            item.core_idea_zh = ""
    for item in hf_items:
        try:
            item.summary_zh, item.core_idea_zh = client.summarize_hf(item)
        except Exception:
            source = item.detail_summary or item.hf_summary or item.summary
            item.summary_zh = fallback_text(source)
            item.core_idea_zh = ""


def process_arxiv(
    items_by_profile,
    config,
    client: DeepSeekClient,
    now: datetime,
    lookback_hours: int,
    llm_concurrency: int = 4,
) -> dict[str, list[ArxivItem]]:
    sections: dict[str, list[ArxivItem]] = {}
    for profile in config.profiles:
        items = items_by_profile.get(profile.id, []) if isinstance(items_by_profile, dict) else list(items_by_profile)
        candidates = rank_arxiv_for_profile(
            items,
            profile,
            max_candidates=config.report.max_arxiv_candidates_per_profile,
            now=now,
            lookback_hours=lookback_hours,
        )
        log(f"profile={profile.id} candidates={len(candidates)}")
        with ThreadPoolExecutor(max_workers=llm_concurrency) as executor:
            rerank_futures = [executor.submit(client.rerank_arxiv, profile, item) for item in candidates]
            for item, future in zip(candidates, rerank_futures, strict=False):
                try:
                    llm_score, verdict, reason_zh = future.result()
                    apply_llm_rerank(item, profile.id, llm_score, verdict, reason_zh)
                except Exception as exc:
                    profile_score = item.profile_scores[profile.id]
                    apply_llm_rerank(item, profile.id, int(profile_score.normalized_rule_score), "relevant", f"LLM 重排失败，回退规则分：{exc}")
        ranked = sorted(candidates, key=lambda item: item.profile_scores[profile.id].final_score, reverse=True)
        selected = ranked[: config.report.max_arxiv_results_per_profile]
        with ThreadPoolExecutor(max_workers=llm_concurrency) as executor:
            summary_futures = [executor.submit(client.summarize_arxiv, item, profile.name) for item in selected]
            for item, future in zip(selected, summary_futures, strict=False):
                try:
                    item.summary_zh, item.core_idea_zh = future.result()
                except Exception:
                    item.summary_zh = fallback_text(item.abstract or item.summary)
                    item.core_idea_zh = ""
        sections[profile.id] = selected
        log(f"profile={profile.id} selected={len(sections[profile.id])}")
    return sections


def write_output(html: str, now: datetime, period: str) -> Path:
    output_dir = ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"digest-{period}-{now.astimezone(UTC).strftime('%Y%m%d-%H%M%S')}.html"
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main() -> int:
    args = parse_args()
    load_dotenv_file(ROOT / ".env")
    load_dotenv_file(ROOT / "secrets.env", override=True)
    if args.env_file:
        load_dotenv_file(Path(args.env_file), override=True)
    config = load_config(ROOT / "config.yaml")
    now = resolve_now(args.now)
    lookback_hours = resolve_lookback_hours(args.period, config.report.lookback_hours)
    llm_concurrency = max(1, int(os.getenv("ARXIV_LLM_CONCURRENCY", "4")))
    log(f"config loaded, lookback_hours={lookback_hours}, period={args.period}")
    window_start = now.astimezone(UTC).timestamp() - (lookback_hours * 3600)
    log(f"window_start={datetime.fromtimestamp(window_start, tz=UTC).isoformat()}")

    session = requests.Session()
    session.headers.update({"User-Agent": "AI-Research-Daily/1.0"})
    store = SeenStore(ROOT / "data" / "seen_cache.json")
    store.load()
    client = DeepSeekClient(session=session)

    arxiv_items_by_profile: dict[str, list[ArxivItem]] = {}
    github_items: list[GithubItem] = []
    hf_items: list[HuggingFaceItem] = []

    for profile in config.profiles:
        try:
            query = build_profile_arxiv_query(profile)
            raw_items = fetch_arxiv_candidates(
                session=None,
                now=now,
                lookback_hours=lookback_hours,
                max_results=config.report.max_arxiv_fetch_results_per_profile,
                search_query=query,
            )
            final_items = filter_items_for_digest(raw_items, "arxiv", lambda item: item.arxiv_id, store, now, lookback_hours)
            arxiv_items_by_profile[profile.id] = final_items
            log(f"arxiv profile={profile.id} fetched_raw={len(raw_items)} skipped={len(raw_items) - len(final_items)} final={len(final_items)}")
        except Exception as exc:
            arxiv_items_by_profile[profile.id] = []
            log(f"arxiv fetch failed for profile={profile.id}: {exc}")

    try:
        raw_github_items = fetch_github_trending(session, period=args.period)
        github_items = filter_items_for_digest(raw_github_items, "github", lambda item: item.repo_name, store, now, lookback_hours)[: config.report.max_github_results]
        enrich_github_items(session, github_items)
        log(f"github fetched_raw={len(raw_github_items)} skipped={len(raw_github_items) - len(github_items)} final={len(github_items)}")
    except Exception as exc:
        log(f"github fetch failed: {exc}")

    try:
        raw_hf_items = fetch_hf_daily_papers(session, period=args.period)
        hf_items = filter_items_for_digest(raw_hf_items, "huggingface", canonical_id_for_hf, store, now, lookback_hours)[: config.report.max_hf_results]
        enrich_hf_items(session, hf_items)
        log(f"huggingface fetched_raw={len(raw_hf_items)} skipped={len(raw_hf_items) - len(hf_items)} final={len(hf_items)}")
    except Exception as exc:
        log(f"huggingface fetch failed: {exc}")

    arxiv_sections = process_arxiv(
        arxiv_items_by_profile,
        config,
        client,
        now=now,
        lookback_hours=lookback_hours,
        llm_concurrency=llm_concurrency,
    )
    summarize_items(client, github_items, hf_items)

    report = RenderedReport(
        generated_at=now,
        lookback_hours=lookback_hours,
        arxiv_sections=arxiv_sections,
        github_items=github_items,
        hf_items=hf_items,
        html="",
        period=args.period,
    )
    report.html = render_email_html(report, profile_names={profile.id: profile.name for profile in config.profiles}, timezone_name=config.report.timezone)
    output_path = write_output(report.html, now, args.period)
    log(f"html output={output_path}")

    should_send = not args.dry_run and not args.skip_send
    send_succeeded = False
    if should_send:
        subject_base = "AI/科研周报" if args.period == "weekly" else "AI/科研日报"
        try:
            send_html_email(
                host=os.getenv("SMTP_HOST", ""),
                port=int(os.getenv("SMTP_PORT", "465")),
                user=os.getenv("SMTP_USER", ""),
                password=os.getenv("SMTP_PASSWORD", ""),
                from_addr=os.getenv("MAIL_FROM", os.getenv("SMTP_USER", "")),
                to_addrs=config.mail_to,
                subject=f"[{now.astimezone(UTC).strftime('%Y-%m-%d')}] {subject_base}",
                html_body=report.html,
            )
            send_succeeded = True
            log("email send success")
        except Exception as exc:
            log(f"email send failed: {exc}")
    else:
        log("email send skipped")

    if send_succeeded:
        sent_at = now
        for sections in arxiv_sections.values():
            mark_sent_for_digest(store, "arxiv", sections, lambda item: item.arxiv_id, sent_at)
        mark_sent_for_digest(store, "github", github_items, lambda item: item.repo_name, sent_at)
        mark_sent_for_digest(store, "huggingface", hf_items, canonical_id_for_hf, sent_at)
        store.save()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
