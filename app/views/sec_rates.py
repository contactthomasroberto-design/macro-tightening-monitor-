from sections import render

render(
    "Rates",
    "Curves, term premium, sovereign spreads and financial conditions.",
    [("Curves and term premium", "curves.py"), ("Financial conditions", "fincond.py")],
    key="rates",
)
