# us-midcap-data

Mid-cap US stocks for chart-ta. Stage A: **S&P MidCap 400 members** (Wikipedia list) minus names already in `us-market-data`. Stage B (planned): Russell 1000 approximation by dollar volume, tagged in `universe.csv` column `list`. Yahoo (yfinance) adjusted daily prices.

| Branch | Contents | Update |
|---|---|---|
| `data` | `prices.parquet` (last 2 years), `universe.csv`, `meta.json` — same layout as us-market-data | weekdays 07:47 KST (+ backups), or push `REFRESH` |
| `history` | `prices_YYYY.parquet` (2005~), `universe.csv`, `meta.json` | monthly, or push `REFRESH_HISTORY` |

Universe = current index membership: the history branch has survivorship and composition bias (reference backtest only). Forward signals are recorded in the private chart-ta sheet, not here.
