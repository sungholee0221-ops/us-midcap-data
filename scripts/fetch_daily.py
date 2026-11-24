"""Daily: last 2 years for the mid-cap universe (layout mirrors us-market-data so chart-ta can read it the same way).

Output (OUT_DIR): prices.parquet (date, ticker, open, high, low, close, volume; adjusted), universe.csv (ticker, name, source),
meta.json (generated_at, last_date, tickers, universe_source, failed, notes).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from common import INDICES, drop_partial, fetch_all, load_universe

OUT_DIR = Path(os.environ.get("OUT_DIR", "out"))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    u, src = load_universe()
    print(f"universe: {len(u)} mid-caps from {src}", flush=True)
    px, missing = fetch_all(u["ticker"].tolist() + INDICES, period="2y")
    px = drop_partial(px).sort_values(["ticker", "date"]).reset_index(drop=True)
    if px["ticker"].nunique() < 0.9 * (len(u) + len(INDICES)):
        print(f"ERROR only {px['ticker'].nunique()} tickers; not publishing", file=sys.stderr)
        return 1
    px.to_parquet(OUT_DIR / "prices.parquet", index=False, compression="zstd")
    u.assign(source="midcap")[["ticker", "name", "source", "list", "sector"]].to_csv(OUT_DIR / "universe.csv", index=False)
    meta = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "last_date": str(px["date"].max()),
            "tickers": int(px["ticker"].nunique()), "universe_source": src, "failed": missing,
            "notes": "S&P MidCap 400 minus names already in us-market-data (stage A). Current membership (forward use)."}
    (OUT_DIR / "meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps({k: v for k, v in meta.items() if k != "failed"}, indent=2), f"failed {len(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
