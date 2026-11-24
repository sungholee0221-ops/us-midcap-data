"""Monthly: full history 2005~ for the same universe (reference backtest only: current membership = survivorship/composition bias).

Output (OUT_DIR): prices_YYYY.parquet, universe.csv, meta.json
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from common import INDICES, drop_partial, fetch_all, load_universe

OUT_DIR = Path(os.environ.get("OUT_DIR", "out"))
START = os.environ.get("START", "2005-01-01")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    u, src = load_universe()
    px, missing = fetch_all(u["ticker"].tolist() + INDICES, start=START)
    px = drop_partial(px).sort_values(["ticker", "date"]).reset_index(drop=True)
    if px["ticker"].nunique() < 0.9 * (len(u) + len(INDICES)):
        print(f"ERROR only {px['ticker'].nunique()} tickers; not publishing", file=sys.stderr)
        return 1
    rows = {}
    for y, g in px.groupby(pd.to_datetime(px["date"]).dt.year):
        g.to_parquet(OUT_DIR / f"prices_{y}.parquet", index=False, compression="zstd")
        rows[int(y)] = int(len(g))
    u.assign(source="midcap")[["ticker", "name", "source"]].to_csv(OUT_DIR / "universe.csv", index=False)
    meta = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "start": START,
            "last_date": str(px["date"].max()), "tickers": int(px["ticker"].nunique()), "universe_source": src,
            "rows_by_year": rows, "failed": missing,
            "notes": "Current Russell 1000 minus large caps: survivorship and composition bias. Reference backtest only."}
    (OUT_DIR / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"last {meta['last_date']} tickers {meta['tickers']} failed {len(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
