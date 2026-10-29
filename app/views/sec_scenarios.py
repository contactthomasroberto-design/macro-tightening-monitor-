from sections import render

render(
    "Scenarios",
    "Configured scenarios with fan charts, your own scenario, and the macro regime.",
    [
        ("Scenario fans", "scenarios.py"),
        ("Simulator", "scenario_simulator.py"),
        ("Regime and views", "regimes.py"),
    ],
    key="scenarios",
)
