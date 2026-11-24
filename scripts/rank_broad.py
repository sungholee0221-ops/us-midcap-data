"""Stage B (monthly): Russell 1000 approximation by liquidity.

Nasdaq Trader symbol directory (official public files) -> common stocks -> 3 months of daily data ->
median daily dollar volume (close x volume, last 63 sessions) -> top 1000 -> minus names already in us-market-data.
Writes lists/r1000_approx.csv on main (ticker, name, exchange, med_dollar_vol, rank).
"""
from __future__ import annotations

import io
import os
import re
import sys
from pathlib import Path

import pandas as pd
import requests

from common import LARGE_URL, UA, fetch_all

BASE = "https://www.nasdaqtrader.com/dynamic/SymDir/"
EXCLUDE = re.compile(r"\bwarrants?\b|\brights?\b|\bunits?\b|preferred|\bnotes?\b|debenture|\bbonds?\b|%|\bfund\b|"
                     r"\betf\b|\betn\b|acquisition corp|depositary shares? represent", re.I)
OUT = Path(os.environ.get("LIST_OUT", "lists/r1000_approx.csv"))
TOP = 1000


def _read(name: str) -> pd.DataFrame:
    r = requests.get(BASE + name, headers=UA, timeout=60)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), sep="|", dtype=str)
    return df[~df.iloc[:, 0].str.startswith("File Creation Time", na=False)]


def directory() -> pd.DataFrame:
    a = _read("nasdaqlisted.txt")
    a = a[(a["Test Issue"] == "N") & (a["ETF"] == "N")]
    a = pd.DataFrame({"symbol": a["Symbol"], "name": a["Security Name"], "exchange": "NASDAQ"})
    b = _read("otherlisted.txt")
    b = b[(b["Test Issue"] == "N") & (b["ETF"] == "N")]
    ex = {"A": "NYSE American", "N": "NYSE", "P": "NYSE Arca", "Z": "Cboe BZX", "V": "IEX"}
    b = pd.DataFrame({"symbol": b["ACT Symbol"], "name": b["Security Name"], "exchange": b["Exchange"].map(ex).fillna(b["Exchange"])})
    u = pd.concat([a, b], ignore_index=True).dropna(subset=["symbol", "name"])
    u = u[~u["name"].str.contains(EXCLUDE) & ~u["symbol"].str.contains(r"[\$\^=]", regex=True)]
    u["ticker"] = u["symbol"].str.replace(".", "-", regex=False)
    return u.drop_duplicates("ticker").reset_index(drop=True)


def main() -> int:
    u = directory()
    print(f"directory common stocks {len(u)}", flush=True)
    px, missing = fetch_all(u["ticker"].tolist(), chunk=100, period="3mo")
    px["dv"] = px["close"] * px["volume"]
    last = px.sort_values("date").groupby("ticker").tail(63)
    med = last.groupby("ticker")["dv"].median().rename("med_dollar_vol")
    top = med.sort_values(ascending=False).head(TOP).reset_index()
    top["rank"] = range(1, len(top) + 1)
    large = set(pd.read_csv(io.StringIO(requests.get(LARGE_URL, timeout=60).text))["ticker"].astype(str))
    top = top[~top["ticker"].isin(large)].merge(u[["ticker", "name", "exchange"]], on="ticker", how="left")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    top[["ticker", "name", "exchange", "med_dollar_vol", "rank"]].to_csv(OUT, index=False)
    print(f"top {TOP} by dollar volume, minus large caps -> {len(top)} names; cutoff ${top['med_dollar_vol'].min():,.0f}/day; "
          f"price fetch missing {len(missing)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
