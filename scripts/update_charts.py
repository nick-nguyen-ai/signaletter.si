#!/usr/bin/env python3
"""Update long-run chart CSVs used by Markets pages (_data/brent.csv, _data/gold.csv).

Sources (see _data/charts.yml):
  brent — FRED DCOILBRENTEU (EIA Europe Brent spot), daily
  gold  — Yahoo Finance GC=F (COMEX gold futures), settled daily close

Idempotent: re-running with no new settled observations exits 0 and leaves files
unchanged. Missing / null / "." values are skipped. Yahoo's in-progress same-day
bar is excluded until the exchange session close has passed.

Usage:
  python3 scripts/update_charts.py
  python3 scripts/update_charts.py --series brent
  python3 scripts/update_charts.py --series gold --dry-run
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "_data"
UA = "Mozilla/5.0 (X11; Linux x86_64) signaletter.si-charts/1.0"
NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc

# COMEX electronic gold session wraps ~17:00 America/New_York on weekdays.
GOLD_SESSION_CLOSE = (17, 0)

SERIES = {
    "brent": {
        "path": "brent.csv",
        "fred_id": "DCOILBRENTEU",
        "source": "FRED DCOILBRENTEU",
    },
    "gold": {
        "path": "gold.csv",
        "yahoo_symbol": "GC=F",
        "source": "Yahoo Finance GC=F",
        "tz": NY,
        "session_close": GOLD_SESSION_CLOSE,
    },
}


# ---------------------------------------------------------------- HTTP

def get(url: str, retries: int = 4, pause: float = 4.0, timeout: float = 60.0) -> str:
    last: Exception | None = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8-sig", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
            time.sleep(pause * (i + 1))
    raise RuntimeError(f"fetch failed {url}: {last}")


# ---------------------------------------------------------------- CSV helpers

def format_close(value: float) -> str:
    """Plain two-decimal close (matches existing brent/gold CSVs)."""
    return f"{float(value):.2f}"


def read_chart_csv(path: Path) -> list[tuple[str, str]]:
    """Return [(date_iso, close_str)] preserving empty closes as ''."""
    if not path.exists():
        return []
    rows: list[tuple[str, str]] = []
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "date" not in reader.fieldnames or "close" not in reader.fieldnames:
            raise ValueError(f"{path}: expected header date,close")
        for r in reader:
            d = (r.get("date") or "").strip()
            if not d:
                continue
            rows.append((d, (r.get("close") or "").strip()))
    return rows


def write_chart_csv(path: Path, rows: list[tuple[str, str]]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["date", "close"])
        for d, c in rows:
            w.writerow([d, c])
    tmp.replace(path)


def last_date(rows: list[tuple[str, str]]) -> dt.date | None:
    if not rows:
        return None
    return dt.date.fromisoformat(rows[-1][0])


def merge_rows(
    existing: list[tuple[str, str]],
    incoming: list[tuple[dt.date, float]],
) -> tuple[list[tuple[str, str]], int]:
    """Merge by date (sorted). Incoming non-empty values fill gaps and update diffs.

    Returns (merged_rows, change_count) where change_count is added + updated cells.
    """
    by_date: dict[str, str] = {d: c for d, c in existing}
    changes = 0
    for d, value in incoming:
        key = d.isoformat()
        formatted = format_close(value)
        old = by_date.get(key)
        if old is None:
            by_date[key] = formatted
            changes += 1
        elif old == "":
            by_date[key] = formatted
            changes += 1
        elif old != formatted:
            by_date[key] = formatted
            changes += 1
    merged = sorted(by_date.items(), key=lambda kv: kv[0])
    return merged, changes


# ---------------------------------------------------------------- FRED (Brent)

def parse_fred_csv(text: str) -> list[tuple[dt.date, float]]:
    """Parse FRED graph CSV; drop missing / null / '.' observations."""
    out: list[tuple[dt.date, float]] = []
    for r in csv.reader(io.StringIO(text)):
        if len(r) < 2 or not r[0][:4].isdigit():
            continue
        raw = (r[1] or "").strip()
        if raw in ("", ".", "nan", "NaN", "null", "None"):
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        out.append((dt.date.fromisoformat(r[0]), value))
    return out


def fetch_fred(series_id: str, since: dt.date) -> list[tuple[dt.date, float]]:
    """Download FRED graph CSV.

    Akamai intermittently stalls some `fredgraph.csv` query shapes. Try short
    attempts across the full series URL and a windowed `cosd` URL.
    """
    sid = urllib.parse.quote(series_id)
    cosd = (since - dt.timedelta(days=7)).isoformat()
    urls = [
        f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}",
        f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={cosd}",
    ]
    last_err: Exception | None = None
    for i in range(6):
        url = urls[i % len(urls)]
        try:
            return parse_fred_csv(get(url, retries=1, pause=1.0, timeout=20.0))
        except RuntimeError as e:
            last_err = e
            time.sleep(1.5 * (1 + i // 2))
    raise RuntimeError(str(last_err) if last_err else f"fetch failed FRED {series_id}")


# ---------------------------------------------------------------- Yahoo (Gold)

def yahoo_settled_through(
    now: dt.datetime,
    session_close: tuple[int, int] = GOLD_SESSION_CLOSE,
) -> dt.date:
    """Latest local session date whose daily bar is treated as settled."""
    local = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    close = dt.datetime(
        local.year, local.month, local.day, session_close[0], session_close[1], tzinfo=local.tzinfo
    )
    if local >= close:
        return local.date()
    return local.date() - dt.timedelta(days=1)


def parse_yahoo_chart(
    payload: dict,
    *,
    now: dt.datetime | None = None,
    session_close: tuple[int, int] = GOLD_SESSION_CLOSE,
    tz: ZoneInfo = NY,
) -> list[tuple[dt.date, float]]:
    """Extract settled daily closes from a Yahoo chart API payload.

    Skips null closes and any bar on/after the unsettled frontier (in-progress
    intraday daily bar for the current session).
    """
    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        err = ((payload.get("chart") or {}).get("error") or {}).get("description")
        raise RuntimeError(f"Yahoo chart empty{': ' + err if err else ''}")
    block = result[0]
    meta = block.get("meta") or {}
    exchange_tz = ZoneInfo(meta.get("exchangeTimezoneName") or str(tz))
    now_local = (now or dt.datetime.now(UTC)).astimezone(exchange_tz)
    frontier = yahoo_settled_through(now_local, session_close)

    timestamps = block.get("timestamp") or []
    closes = ((block.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    by_day: dict[dt.date, float] = {}
    for t, c in zip(timestamps, closes):
        if c is None:
            continue
        try:
            value = float(c)
        except (TypeError, ValueError):
            continue
        local = dt.datetime.fromtimestamp(int(t), UTC).astimezone(exchange_tz)
        if local.date() > frontier:
            continue
        # Prefer the last print for a session date (Yahoo sometimes repeats).
        by_day[local.date()] = value
    return sorted(by_day.items())


def fetch_yahoo(
    symbol: str,
    since: dt.date,
    *,
    now: dt.datetime | None = None,
    session_close: tuple[int, int] = GOLD_SESSION_CLOSE,
    tz: ZoneInfo = NY,
) -> list[tuple[dt.date, float]]:
    time.sleep(2)  # polite: bursts trigger HTTP 429
    start = since - dt.timedelta(days=7)
    period1 = int(dt.datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp())
    period2 = int((now or dt.datetime.now(UTC)).timestamp()) + 86400
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
        f"?period1={period1}&period2={period2}&interval=1d&includePrePost=false"
    )
    payload = json.loads(get(url, retries=4, pause=8))
    return parse_yahoo_chart(payload, now=now, session_close=session_close, tz=tz)


# ---------------------------------------------------------------- update one series

def update_series(
    name: str,
    data_dir: Path,
    *,
    dry_run: bool = False,
    now: dt.datetime | None = None,
    fetcher=None,
) -> dict:
    cfg = SERIES[name]
    path = data_dir / cfg["path"]
    existing = read_chart_csv(path)
    since = last_date(existing) or dt.date(2020, 1, 1)

    if fetcher is not None:
        incoming = fetcher(since)
    elif "fred_id" in cfg:
        incoming = fetch_fred(cfg["fred_id"], since)
    else:
        incoming = fetch_yahoo(
            cfg["yahoo_symbol"],
            since,
            now=now,
            session_close=cfg.get("session_close", GOLD_SESSION_CLOSE),
            tz=cfg.get("tz", NY),
        )

    # Only keep observations on/after the file start; ignore ancient overlap noise.
    start_keep = dt.date.fromisoformat(existing[0][0]) if existing else dt.date(2020, 1, 1)
    incoming = [(d, v) for d, v in incoming if d >= start_keep]

    merged, changes = merge_rows(existing, incoming)
    latest = merged[-1][0] if merged else None
    latest_close = merged[-1][1] if merged else None

    if changes == 0:
        return {
            "series": name,
            "path": str(path),
            "changed": False,
            "changes": 0,
            "latest": latest,
            "latest_close": latest_close,
            "source": cfg["source"],
        }

    if not dry_run:
        write_chart_csv(path, merged)

    return {
        "series": name,
        "path": str(path),
        "changed": True,
        "changes": changes,
        "latest": latest,
        "latest_close": latest_close,
        "source": cfg["source"],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--series",
        choices=["all", "brent", "gold"],
        default="all",
        help="Which chart CSV to update (default: all)",
    )
    p.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"Directory containing brent.csv / gold.csv (default: {DEFAULT_DATA_DIR})",
    )
    p.add_argument("--dry-run", action="store_true", help="Fetch and merge but do not write files")
    args = p.parse_args(argv)

    names = ["brent", "gold"] if args.series == "all" else [args.series]
    data_dir = args.data_dir
    if not data_dir.is_dir():
        print(f"error: data dir not found: {data_dir}", file=sys.stderr)
        return 2

    any_changed = False
    errors: list[str] = []
    for name in names:
        try:
            result = update_series(name, data_dir, dry_run=args.dry_run)
        except RuntimeError as e:
            print(f"error: {name}: {e}", file=sys.stderr)
            errors.append(name)
            continue
        any_changed = any_changed or result["changed"]
        tag = "updated" if result["changed"] else "up-to-date"
        if args.dry_run and result["changed"]:
            tag = "dry-run"
        print(
            f"{name}: {tag} (+{result['changes']} row changes) "
            f"latest={result['latest']} close={result['latest_close']} "
            f"via {result['source']}"
        )

    if errors:
        print(f"Failed series: {', '.join(errors)}", file=sys.stderr)
        return 1
    if not any_changed:
        print("No chart CSV changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
