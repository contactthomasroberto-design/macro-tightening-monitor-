from sections import render

render(
    "Rates",
    "Curves, term premium, sovereign spreads and financial conditions.",
    [
        ("Curves and term premium", "curves.py"),
        ("Carry and roll-down", "carry.py"),
        ("Financial conditions", "fincond.py"),
    ],
    key="rates",
)
