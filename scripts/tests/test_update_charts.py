#!/usr/bin/env python3
"""Unit tests for scripts/update_charts.py (no network).

Run: python3 scripts/tests/test_update_charts.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import update_charts as uc  # noqa: E402

NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc


def test_format_close_two_decimals():
    assert uc.format_close(126.5) == "126.50"
    assert uc.format_close(4181.1) == "4181.10"
    assert uc.format_close(91) == "91.00"


def test_parse_fred_skips_missing_and_dots():
    text = "\n".join(
        [
            "observation_date,DCOILBRENTEU",
            "2026-10-14,126.55",
            "2026-10-15,.",
            "2026-10-16,",
            "2026-10-17,null",
            "2026-10-20,127.4",
        ]
    )
    rows = uc.parse_fred_csv(text)
    assert rows == [
        (dt.date(2026, 10, 14), 126.55),
        (dt.date(2026, 10, 20), 127.4),
    ]


def test_yahoo_settled_through_before_and_after_close():
    before = dt.datetime(2026, 11, 26, 16, 59, tzinfo=NY)
    after = dt.datetime(2026, 11, 26, 17, 0, tzinfo=NY)
    assert uc.yahoo_settled_through(before) == dt.date(2026, 11, 25)
    assert uc.yahoo_settled_through(after) == dt.date(2026, 11, 26)


def test_parse_yahoo_skips_null_and_intraday_bar():
    # Completed days stamp midnight ET; in-progress day stamps afternoon.
    payload = {
        "chart": {
            "result": [
                {
                    "meta": {"exchangeTimezoneName": "America/New_York"},
                    "timestamp": [
                        int(dt.datetime(2026, 11, 24, 0, 0, tzinfo=NY).timestamp()),
                        int(dt.datetime(2026, 11, 25, 0, 0, tzinfo=NY).timestamp()),
                        int(dt.datetime(2026, 11, 26, 14, 30, tzinfo=NY).timestamp()),
                    ],
                    "indicators": {"quote": [{"close": [3561.8999, 3535.8, None]}]},
                }
            ],
            "error": None,
        }
    }
    # Market still open on 26 Nov → frontier is 25 Nov; None close already dropped.
    now = dt.datetime(2026, 11, 26, 16, 0, tzinfo=NY)
    rows = uc.parse_yahoo_chart(payload, now=now)
    assert rows == [
        (dt.date(2026, 11, 24), 3561.8999),
        (dt.date(2026, 11, 25), 3535.8),
    ]

    # After session close, a real close on the 26th is kept.
    payload["chart"]["result"][0]["indicators"]["quote"][0]["close"] = [3561.9, 3535.8, 3593.4]
    rows_after = uc.parse_yahoo_chart(
        payload, now=dt.datetime(2026, 11, 26, 17, 5, tzinfo=NY)
    )
    assert rows_after[-1] == (dt.date(2026, 11, 26), 3593.4)


def test_parse_yahoo_dedupes_last_bar_wins():
    payload = {
        "chart": {
            "result": [
                {
                    "meta": {"exchangeTimezoneName": "America/New_York"},
                    "timestamp": [
                        int(dt.datetime(2026, 11, 25, 0, 0, tzinfo=NY).timestamp()),
                        int(dt.datetime(2026, 11, 25, 12, 0, tzinfo=NY).timestamp()),
                    ],
                    "indicators": {"quote": [{"close": [3500.0, 3535.8]}]},
                }
            ]
        }
    }
    rows = uc.parse_yahoo_chart(payload, now=dt.datetime(2026, 11, 26, 12, 0, tzinfo=NY))
    assert rows == [(dt.date(2026, 11, 25), 3535.8)]


def test_merge_rows_adds_fills_updates_and_sorts():
    existing = [
        ("2026-10-14", "126.55"),
        ("2026-10-15", ""),  # gap to fill
        ("2026-10-20", "130.00"),  # will be revised
    ]
    incoming = [
        (dt.date(2026, 10, 15), 127.10),
        (dt.date(2026, 10, 16), 128.25),
        (dt.date(2026, 10, 20), 129.50),
        (dt.date(2026, 10, 14), 126.55),  # identical → no change
    ]
    merged, changes = uc.merge_rows(existing, incoming)
    assert changes == 3  # fill + add + revise
    assert merged == [
        ("2026-10-14", "126.55"),
        ("2026-10-15", "127.10"),
        ("2026-10-16", "128.25"),
        ("2026-10-20", "129.50"),
    ]


def test_merge_idempotent_when_unchanged():
    existing = [("2026-10-14", "126.55"), ("2026-10-16", "128.25")]
    incoming = [(dt.date(2026, 10, 14), 126.55), (dt.date(2026, 10, 16), 128.25)]
    merged, changes = uc.merge_rows(existing, incoming)
    assert changes == 0
    assert merged == existing


def test_read_write_roundtrip(tmp_path: Path | None = None):
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "brent.csv"
        rows = [("2026-10-14", "126.55"), ("2026-10-15", ""), ("2026-10-16", "128.25")]
        uc.write_chart_csv(path, rows)
        text = path.read_text()
        assert text.splitlines()[0] == "date,close"
        assert "2026-10-15," in text.splitlines()
        assert uc.read_chart_csv(path) == rows


def test_update_series_noop_and_write(monkey_now=None):
    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        path = data_dir / "brent.csv"
        uc.write_chart_csv(path, [("2026-10-14", "126.55")])

        def no_new(_since):
            return [(dt.date(2026, 10, 14), 126.55)]

        r = uc.update_series("brent", data_dir, fetcher=no_new)
        assert r["changed"] is False and r["changes"] == 0
        assert path.read_text() == "date,close\n2026-10-14,126.55\n"

        def add_rows(_since):
            return [
                (dt.date(2026, 10, 14), 126.55),
                (dt.date(2026, 10, 15), 127.4),
                (dt.date(2026, 11, 24), 91.8),
            ]

        r2 = uc.update_series("brent", data_dir, fetcher=add_rows)
        assert r2["changed"] is True and r2["changes"] == 2
        assert r2["latest"] == "2026-11-24"
        assert r2["latest_close"] == "91.80"
        body = path.read_text().splitlines()
        assert body[-1] == "2026-11-24,91.80"
        assert "2026-10-15,127.40" in body


def test_update_series_dry_run_does_not_write():
    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        path = data_dir / "gold.csv"
        uc.write_chart_csv(path, [("2026-10-16", "4181.10")])
        before = path.read_text()

        def add(_since):
            return [(dt.date(2026, 11, 25), 3535.8)]

        r = uc.update_series("gold", data_dir, dry_run=True, fetcher=add)
        assert r["changed"] is True and r["changes"] == 1
        assert path.read_text() == before


def test_cli_bad_data_dir():
    code = uc.main(["--data-dir", "/no/such/dir/charts", "--series", "brent"])
    assert code == 2


def test_cli_network_error_is_exit_1(monkeypatch=None):
    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        uc.write_chart_csv(data_dir / "brent.csv", [("2026-10-14", "126.55")])

        def boom(*_a, **_k):
            raise RuntimeError("fetch failed https://example: timed out")

        # Patch fetch_fred used inside update_series when no fetcher injected —
        # drive via main by patching the module function.
        orig = uc.fetch_fred
        uc.fetch_fred = boom  # type: ignore[assignment]
        try:
            code = uc.main(["--data-dir", str(data_dir), "--series", "brent"])
            assert code == 1
        finally:
            uc.fetch_fred = orig  # type: ignore[assignment]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("ok  ", name)
            except AssertionError as e:
                fails += 1
                print("FAIL", name, e)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("ERROR", name, type(e).__name__, e)
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
