"""Shared helpers: universe (Russell 1000 minus S&P 500 / Nasdaq-100 names already in us-market-data) and yfinance download.

Universe sources (tried in order):
  1. iShares Russell 1000 ETF (IWB) holdings CSV
  2. Wikipedia "Russell 1000 Index" components table
Large caps already covered by us-market-data (read-only, never written) are removed.
"""
from __future__ import annotations

import io
import time

import pandas as pd
import requests
import yfinance as yf

IWB_URL = ("https://www.ishares.com/us/products/239707/ishares-russell-1000-etf/1467271812596.ajax"
           "?fileType=csv&fileName=IWB_holdings&dataType=fund")
WIKI_URL = "https://en.wikipedia.org/wiki/Russell_1000_Index"
LARGE_URL = "https://raw.githubusercontent.com/sungholee0221-ops/us-market-data/data/universe.csv"
UA = {"User-Agent": "Mozilla/5.0 (chart-ta research; github.com/sungholee0221-ops)"}
INDICES = ["^GSPC", "^RUI", "^RUT", "^VIX"]


def _iwb() -> pd.DataFrame:
    resp = requests.get(IWB_URL, headers=UA, timeout=60)
    txt = resp.content.decode("utf-8-sig", errors="replace")
    lines = txt.splitlines()
    print(f"IWB status {resp.status_code} type {resp.headers.get('content-type')} len {len(txt)} head {txt[:200]!r}", flush=True)
    start = next((i for i, l in enumerate(lines) if l.lstrip('\ufeff"').startswith("Ticker")), None)
    if start is None:
        raise RuntimeError("no Ticker header in IWB response")
    df = pd.read_csv(io.StringIO("\n".join(lines[start:])))
    df = df[df["Asset Class"].astype(str).str.lower().eq("equity")]
    return pd.DataFrame({"ticker": df["Ticker"].astype(str).str.strip(), "name": df["Name"].astype(str),
                         "sector": df.get("Sector", "")})


def _wiki() -> pd.DataFrame:
    resp = requests.get(WIKI_URL, headers=UA, timeout=60)
    html = resp.text
    tables = pd.read_html(io.StringIO(html))
    print(f"wiki status {resp.status_code} tables {[(t.shape, [str(c) for c in t.columns][:4]) for t in tables]}", flush=True)
    for t in tables:
        cols = {str(c).lower(): c for c in t.columns}
        sym = next((cols[c] for c in cols if "symbol" in c or "ticker" in c), None)
        name = next((cols[c] for c in cols if "company" in c or "name" in c), None)
        if sym is not None and len(t) > 900:
            return pd.DataFrame({"ticker": t[sym].astype(str).str.strip(),
                                 "name": t[name].astype(str) if name is not None else "",
                                 "sector": t[cols["gics sector"]] if "gics sector" in cols else ""})
    raise RuntimeError("Russell 1000 table not found on Wikipedia")


def load_universe() -> tuple[pd.DataFrame, str]:
    try:
        r, src = _iwb(), "iShares IWB holdings"
        if len(r) < 900:
            raise RuntimeError(f"IWB holdings only {len(r)} rows")
    except Exception as e:  # noqa: BLE001
        print(f"IWB failed ({e}); using Wikipedia", flush=True)
        r, src = _wiki(), "Wikipedia Russell 1000"
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
