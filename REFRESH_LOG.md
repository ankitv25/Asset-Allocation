# Refresh log

One row per scheduled refresh (Mon / Wed / Fri, 07:00 local), written by `scheduled_refresh.sh` and
committed with the payloads it produced. A failed run is recorded too, with the step it stopped at; its
outputs are discarded, so the dashboard keeps the last good refresh. Runs stopped by the safety checks
(uncommitted work, unpushed commits) never touch the repo and appear only in
`~/Library/Logs/summer_dashboard_refresh.log`. How the refresh works: [UPDATING.md](UPDATING.md).

| Run (local) | Priced to | Previous close | Steps (seconds) | Minutes | Result |
|---|---|---|---|---|---|
| Thu 2026-10-01 19:08 | 2026-10-01 | 2026-09-25 | fund_nav 3s · vehicle_data 4s · factor_attrib 1s · pit_backtest 1s · style_box 1s · fi_style_box 0s · build_portfolios_dashboard_data 1s · build_portfolio_books_data 5s · pc_fund_live_page 0s · verify_dashboard 0s | 0 | published · 13 file(s) changed |
