"""Shared helpers: universe and yfinance download.

Stage A (2026-11-24): S&P MidCap 400 members from Wikipedia, minus names already in us-market-data (read-only).
Stage B (planned): Russell 1000 approximation (top 1000 by 3-month dollar volume from the Nasdaq Trader symbol
directory) added as a union with a `list` tag.
"""
from __future__ import annotations

import io
import time
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

SP400_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
LARGE_URL = "https://raw.githubusercontent.com/sungholee0221-ops/us-market-data/data/universe.csv"
UA = {"User-Agent": "chart-ta-research/1.0 (personal research; github.com/sungholee0221-ops/us-midcap-data)"}
INDICES = ["^GSPC", "^MID", "^RUT", "^VIX"]


def _sp400() -> pd.DataFrame:
    """1단계(A): S&P MidCap 400 구성 종목(위키백과 표)."""
    resp = requests.get(SP400_URL, headers=UA, timeout=60)
    resp.raise_for_status()
    for t in pd.read_html(io.StringIO(resp.text)):
        cols = {str(c).lower(): c for c in t.columns}
        sym = next((cols[c] for c in cols if c in ("symbol", "ticker symbol", "ticker")), None)
        if sym is not None and len(t) >= 350:
            name = next((cols[c] for c in cols if c in ("security", "company")), None)
            sec = next((cols[c] for c in cols if "sector" in c), None)
            return pd.DataFrame({"ticker": t[sym].astype(str).str.strip(),
                                 "name": t[name].astype(str) if name is not None else "",
                                 "sector": t[sec].astype(str) if sec is not None else "", "list": "sp400"})
    raise RuntimeError("S&P 400 table not found")


B_LIST = Path(__file__).resolve().parents[1] / "lists" / "r1000_approx.csv"


def load_universe() -> tuple[pd.DataFrame, str]:
    """A(S&P 400) ∪ B(러셀 1000 근사, lists/r1000_approx.csv가 있으면). list 열: sp400 / r1000x / sp400+r1000x."""
    r, src = _sp400(), "Wikipedia List of S&P 400 companies"
    print(f"S&P 400 rows {len(r)}", flush=True)
    if B_LIST.exists():
        b = pd.read_csv(B_LIST)
        b = pd.DataFrame({"ticker": b["ticker"].astype(str), "name": b["name"].astype(str), "sector": "", "list": "r1000x"})
        both = set(r["ticker"]) & set(b["ticker"])
        r.loc[r["ticker"].isin(both), "list"] = "sp400+r1000x"
        r = pd.concat([r, b[~b["ticker"].isin(set(r["ticker"]))]], ignore_index=True)
        src += f" + Russell 1000 approx ({len(b)}; overlap {len(both)})"
        print(f"B list rows {len(b)}, overlap with S&P 400 {len(both)}", flush=True)
    r["ticker"] = r["ticker"].str.replace(".", "-", regex=False).str.replace(" ", "-", regex=False)
    r = r[r["ticker"].str.fullmatch(r"[A-Z][A-Z0-9\-]{0,6}")]
    large = pd.read_csv(io.StringIO(requests.get(LARGE_URL, timeout=60).text))["ticker"].astype(str)
    u = r[~r["ticker"].isin(set(large))].drop_duplicates("ticker").sort_values("ticker").reset_index(drop=True)
    return u, src


def download(tickers: list[str], **kw) -> pd.DataFrame:
    df = yf.download(tickers, interval="1d", auto_adjust=True, group_by="ticker", threads=True, progress=False, **kw)
    if df.empty:
        return pd.DataFrame()
    if not isinstance(df.columns, pd.MultiIndex):
        df.columns = pd.MultiIndex.from_product([tickers, df.columns])
    long = df.stack(level=0, future_stack=True).reset_index()
    long.columns = [str(c).lower() for c in long.columns]
    long = long.rename(columns={long.columns[0]: "date", long.columns[1]: "ticker"})
    long = long.dropna(subset=["close"])
    return long[["date", "ticker", "open", "high", "low", "close", "volume"]]


def fetch_all(tickers: list[str], chunk: int = 50, **kw) -> tuple[pd.DataFrame, list[str]]:
    parts, missing = [], []
    for i in range(0, len(tickers), chunk):
        c = tickers[i: i + chunk]
        try:
            got = download(c, **kw)
        except Exception as e:  # noqa: BLE001
            print(f"chunk {i} error {e}", flush=True)
            got = pd.DataFrame()
        parts.append(got)
        missing += sorted(set(c) - set(got["ticker"])) if not got.empty else c
        time.sleep(2)
    if missing:
        time.sleep(20)
        still = []
        for i in range(0, len(missing), 10):
            c = missing[i: i + 10]
            try:
                got = download(c, **kw)
            except Exception:  # noqa: BLE001
                got = pd.DataFrame()
            parts.append(got)
            still += sorted(set(c) - set(got["ticker"])) if not got.empty else c
            time.sleep(3)
        missing = still
    px = pd.concat([p for p in parts if not p.empty], ignore_index=True)
    px["date"] = pd.to_datetime(px["date"]).dt.date
    px["volume"] = px["volume"].fillna(0).astype("int64")
    for c in ["open", "high", "low", "close"]:
        px[c] = px[c].astype("float64").round(4)
    return px, missing


def drop_partial(px: pd.DataFrame) -> pd.DataFrame:
    """Drop a recent session present for only some tickers (run during market hours)."""
    per_day = px.groupby("date")["ticker"].nunique()
    partial = per_day[per_day < 0.5 * per_day.tail(250).median()].index
    recent = [d for d in partial if (per_day.index.max() - d).days <= 7]
    if recent:
        print(f"dropping partial recent dates: {[str(d) for d in recent]}", flush=True)
        px = px[~px["date"].isin(recent)]
    return px
