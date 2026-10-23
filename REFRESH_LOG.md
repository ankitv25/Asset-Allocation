# Refresh log

One row per scheduled refresh (Mon / Wed / Fri, 07:00 New York, GitHub Actions), written by `scheduled_refresh.sh` and
committed with the payloads it produced. A failed run is recorded too, with the step it stopped at; its
outputs are discarded, so the dashboard keeps the last good refresh. Runs stopped by the safety checks
(uncommitted work, unpushed commits) never touch the repo and appear only in the
Actions run log. How the refresh works: [UPDATING.md](UPDATING.md).

| Run (local) | Priced to | Previous close | Steps | Total | Result |
|---|---|---|---|---|---|
| Thu 2026-10-01 19:08 | 2026-10-01 | 2026-09-25 | fund_nav 3s · vehicle_data 4s · factor_attrib 1s · pit_backtest 1s · style_box 1s · fi_style_box 0s · build_portfolios_dashboard_data 1s · build_portfolio_books_data 5s · pc_fund_live_page 0s · verify_dashboard 0s | 25s | published · 13 file(s) changed |
| Mon 2026-10-05 15:28 | — | 2026-10-01 |  | 2s | **failed** at `fund_nav`: step failed at line 55 — see the run log |
| Wed 2026-10-07 13:38 | — | 2026-10-01 |  | 3s | **failed** at `fund_nav`: step failed at line 55 — see the run log |
| Fri 2026-10-09 13:16 | — | 2026-10-01 |  | 3s | **failed** at `fund_nav`: step failed at line 55 — see the run log |
| Mon 2026-10-12 16:04 | — | 2026-10-01 |  | 1s | **failed** at `fund_nav`: step failed at line 55 — see the run log |
| Wed 2026-10-14 11:40 | — | 2026-10-01 |  | 3s | **failed** at `fund_nav`: step failed at line 55 — see the run log |
| Fri 2026-10-16 11:06 | — | 2026-10-01 |  | 3s | **failed** at `fund_nav`: step failed at line 55 — see the run log |
| Fri 2026-10-16 16:30 | 2026-10-16 | 2026-10-01 | fund_nav 10s · vehicle_data 4s · factor_attrib 1s · pit_backtest 3s · style_box 1s · fi_style_box 0s · build_portfolios_dashboard_data 2s · build_portfolio_books_data 15s · pc_fund_live_page 1s · verify_dashboard 0s | 38s | published · 16 file(s) changed |
| Mon 2026-10-19 13:18 | 2026-10-19 | 2026-10-16 | fund_nav 10s · vehicle_data 6s · factor_attrib 0s · pit_backtest 3s · style_box 1s · fi_style_box 0s · build_portfolios_dashboard_data 1s · build_portfolio_books_data 10s · pc_fund_live_page 1s · verify_dashboard 0s | 32s | published · 25 file(s) changed |
| Wed 2026-10-21 11:47 | 2026-10-21 | 2026-10-19 | fund_nav 8s · vehicle_data 6s · factor_attrib 0s · pit_backtest 3s · style_box 0s · fi_style_box 0s · build_portfolios_dashboard_data 1s · build_portfolio_books_data 10s · pc_fund_live_page 1s · verify_dashboard 0s | 30s | published · 25 file(s) changed |
| Fri 2026-10-23 11:36 | 2026-10-23 | 2026-10-21 | fund_nav 6s · vehicle_data 7s · factor_attrib 0s · pit_backtest 2s · style_box 0s · fi_style_box 0s · build_portfolios_dashboard_data 1s · build_portfolio_books_data 5s · pc_fund_live_page 1s · verify_dashboard 0s | 23s | published · 26 file(s) changed |
