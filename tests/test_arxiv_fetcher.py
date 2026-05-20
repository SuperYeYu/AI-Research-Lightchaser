from __future__ import annotations

import io
import urllib.error
from datetime import UTC, datetime

from src.fetchers.arxiv_fetcher import build_arxiv_query, build_profile_arxiv_query, fetch_arxiv_candidates, parse_arxiv_atom
from src.models import ProfileConfig


def test_parse_arxiv_atom_filters_to_last_24_hours() -> None:
    now = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)
    xml_payload = """
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2605.00001v1</id>
    <published>2026-05-19T01:00:00Z</published>
    <title>Recent Agent Paper</title>
    <summary>Agent planning and tool use</summary>
    <author><name>Alice</name></author>
    <category term="cs.AI" />
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2605.00002v1</id>
    <published>2026-05-18T10:59:59Z</published>
    <title>Old Paper</title>
    <summary>Old summary</summary>
    <author><name>Bob</name></author>
    <category term="cs.LG" />
  </entry>
</feed>
""".strip()

    items = parse_arxiv_atom(xml_payload, now=now, lookback_hours=24)

    assert [item.arxiv_id for item in items] == ["2605.00001v1"]
    assert items[0].authors == ["Alice"]
    assert items[0].categories == ["cs.AI"]


def test_build_arxiv_query_uses_graph_and_multi_agent_friendly_categories() -> None:
    query = build_arxiv_query()

    assert "cat:cs.AI" in query
    assert "cat:cs.CL" in query
    assert "cat:cs.LG" in query
    assert "cat:cs.MA" in query
    assert "cat:cs.SI" in query
    assert "cat:cs.IR" not in query


def test_build_profile_arxiv_query_uses_title_and_abstract_keywords() -> None:
    profile = ProfileConfig(
        id="graph",
        name="Graph / GNN",
        description="graph field",
        keywords=["graph neural network", "GNN"],
        queries=["graph query"],
    )

    query = build_profile_arxiv_query(profile)

    assert 'ti:"graph neural network"' in query
    assert 'abs:"graph neural network"' in query
    assert "ti:GNN" in query
    assert "abs:GNN" in query


def test_fetch_arxiv_candidates_retries_on_429() -> None:
    calls = 0

    class FakeUrlOpenResponse:
        def __init__(self, payload: bytes) -> None:
            self.payload = payload

        def read(self) -> bytes:
            return self.payload

        def __enter__(self) -> "FakeUrlOpenResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    def fake_urlopen(request, timeout: int):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", hdrs=None, fp=io.BytesIO(b""))
        return FakeUrlOpenResponse(
            """
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2605.00003v1</id>
    <published>2026-05-19T02:00:00Z</published>
    <title>Recovered Paper</title>
    <summary>Recovered abstract</summary>
    <author><name>Retry</name></author>
    <category term="cs.AI" />
  </entry>
</feed>
""".strip().encode("utf-8")
        )

    sleep_calls: list[float] = []

    items = fetch_arxiv_candidates(
        session=None,
        now=datetime(2026, 5, 19, 12, 0, tzinfo=UTC),
        lookback_hours=24,
        sleep_fn=sleep_calls.append,
        urlopen_fn=fake_urlopen,
    )

    assert [item.arxiv_id for item in items] == ["2605.00003v1"]
    assert calls == 3
    assert len(sleep_calls) == 2


def test_fetch_arxiv_candidates_retries_on_transient_url_error() -> None:
    calls = 0

    class FakeUrlOpenResponse:
        def __init__(self, payload: bytes) -> None:
            self.payload = payload

        def read(self) -> bytes:
            return self.payload

        def __enter__(self) -> "FakeUrlOpenResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    def fake_urlopen(request, timeout: int):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise urllib.error.URLError("SSL EOF")
        return FakeUrlOpenResponse(
            """
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2605.00005v1</id>
    <published>2026-05-19T04:00:00Z</published>
    <title>Recovered After Transient Error</title>
    <summary>Recovered abstract</summary>
    <author><name>Retry</name></author>
    <category term="cs.AI" />
  </entry>
</feed>
""".strip().encode("utf-8")
        )

    sleep_calls: list[float] = []
    items = fetch_arxiv_candidates(
        session=None,
        now=datetime(2026, 5, 19, 12, 0, tzinfo=UTC),
        lookback_hours=24,
        sleep_fn=sleep_calls.append,
        urlopen_fn=fake_urlopen,
    )

    assert [item.arxiv_id for item in items] == ["2605.00005v1"]
    assert calls == 2
    assert len(sleep_calls) == 1


def test_fetch_arxiv_candidates_supports_urllib_style_fetcher() -> None:
    class FakeUrlOpenResponse:
        def __init__(self, payload: bytes) -> None:
            self.payload = payload

        def read(self) -> bytes:
            return self.payload

        def __enter__(self) -> "FakeUrlOpenResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    calls: list[str] = []

    def fake_urlopen(request, timeout: int):
        calls.append(request.full_url)
        payload = """
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2605.00004v1</id>
    <published>2026-05-19T03:00:00Z</published>
    <title>urllib Paper</title>
    <summary>urllib abstract</summary>
    <author><name>UrlLib</name></author>
    <category term="cs.AI" />
  </entry>
</feed>
""".strip().encode("utf-8")
        return FakeUrlOpenResponse(payload)

    items = fetch_arxiv_candidates(
        session=None,
        now=datetime(2026, 5, 19, 12, 0, tzinfo=UTC),
        lookback_hours=24,
        urlopen_fn=fake_urlopen,
    )

    assert [item.arxiv_id for item in items] == ["2605.00004v1"]
    assert len(calls) == 1
