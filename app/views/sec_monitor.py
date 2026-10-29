from sections import render

render(
    "Market monitor",
    "What moved, by how much relative to its own history, and how stressed markets are.",
    [("Cross-asset", "markets_monitor.py"), ("Credit and volatility", "markets_credit_vol.py")],
    key="monitor",
)
