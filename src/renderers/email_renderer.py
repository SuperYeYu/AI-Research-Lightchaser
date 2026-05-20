from __future__ import annotations

import html
from zoneinfo import ZoneInfo

from src.models import ArxivItem, GithubItem, HuggingFaceItem, RenderedReport


def _format_dt(value, timezone_name: str) -> str:
    if value is None:
        return "-"
    return value.astimezone(ZoneInfo(timezone_name)).strftime("%Y-%m-%d %H:%M")


def _render_empty(message: str) -> str:
    return f"<p style='color:#666;'>{html.escape(message)}</p>"


def _render_arxiv_item(item: ArxivItem, profile_id: str, timezone_name: str) -> str:
    score = item.profile_scores[profile_id]
    return (
        "<li style='margin-bottom:18px;'>"
        f"<div><a href='{html.escape(item.url)}'><strong>{html.escape(item.title)}</strong></a></div>"
        f"<div style='color:#666;font-size:13px;'>作者：{html.escape(', '.join(item.authors) or '-')}</div>"
        f"<div style='color:#666;font-size:13px;'>发布时间：{html.escape(_format_dt(item.published_at, timezone_name))}</div>"
        f"<div style='color:#666;font-size:13px;'>相关性分数：{score.final_score:.1f}</div>"
        f"<div style='margin-top:6px;line-height:1.6;'><strong>中文摘要：</strong>{html.escape(item.summary_zh or item.summary)}</div>"
        f"<div style='margin-top:4px;line-height:1.6;'><strong>相关性理由：</strong>{html.escape(score.reason_zh or '规则排序候选')}</div>"
        "</li>"
    )


def _render_github_item(item: GithubItem) -> str:
    return (
        "<li style='margin-bottom:18px;'>"
        f"<div><a href='{html.escape(item.url)}'><strong>{html.escape(item.repo_name)}</strong></a></div>"
        f"<div style='color:#666;font-size:13px;'>language: {html.escape(item.language or '-')} | today stars: {item.stars_today} | total stars: {item.stars_total}</div>"
        f"<div style='margin-top:6px;line-height:1.6;'><strong>中文摘要：</strong>{html.escape(item.summary_zh or item.description or item.summary)}</div>"
        "</li>"
    )


def _render_hf_item(item: HuggingFaceItem) -> str:
    return (
        "<li style='margin-bottom:18px;'>"
        f"<div><a href='{html.escape(item.url)}'><strong>{html.escape(item.title)}</strong></a></div>"
        f"<div style='margin-top:6px;line-height:1.6;'><strong>中文摘要：</strong>{html.escape(item.summary_zh or item.detail_summary or item.hf_summary or item.summary)}</div>"
        "</li>"
    )


def render_email_html(report: RenderedReport, profile_names: dict[str, str], timezone_name: str) -> str:
    generated = report.generated_at.astimezone(ZoneInfo(timezone_name)).strftime("%Y-%m-%d %H:%M")
    report_title = "AI/科研周报" if report.period == "weekly" else "AI/科研日报"
    arxiv_sections_html: list[str] = []
    for profile_id, items in report.arxiv_sections.items():
        title = profile_names.get(profile_id, profile_id)
        body = "<ul>" + "".join(_render_arxiv_item(item, profile_id, timezone_name) for item in items) + "</ul>" if items else _render_empty("今日无新条目")
        arxiv_sections_html.append(f"<h3>{html.escape(title)}</h3>{body}")
    if not arxiv_sections_html:
        arxiv_sections_html.append(_render_empty("今日无新条目"))
    github_html = "<ul>" + "".join(_render_github_item(item) for item in report.github_items) + "</ul>" if report.github_items else _render_empty("今日无新条目")
    hf_html = "<ul>" + "".join(_render_hf_item(item) for item in report.hf_items) + "</ul>" if report.hf_items else _render_empty("今日无新条目")
    return (
        "<html><body style='font-family:Arial,Microsoft YaHei,sans-serif;line-height:1.6;'>"
        f"<h1>{html.escape(report_title)}</h1><p>生成时间：{html.escape(generated)} | 时间窗：最近 {report.lookback_hours} 小时</p>"
        f"<p>arXiv {sum(len(items) for items in report.arxiv_sections.values())} 条 | GitHub {len(report.github_items)} 条 | Hugging Face Papers {len(report.hf_items)} 条</p>"
        f"<h2>arXiv</h2>{''.join(arxiv_sections_html)}"
        f"<hr /><h2>GitHub Daily Trending</h2>{github_html}"
        f"<hr /><h2>Hugging Face Papers</h2>{hf_html}"
        "</body></html>"
    )
