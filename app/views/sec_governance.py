from sections import render

render(
    "Governance",
    "Forecast track record, data freshness, model cards and notes.",
    [
        ("Track record", "track_record.py"),
        ("Data health", "data_health.py"),
        ("Model cards", "model_cards.py"),
    ],
    key="governance",
)
