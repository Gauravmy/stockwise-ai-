"""Deterministic SYNTHETIC sample sales data (fixed random seed).

The data is generated, not real. Products are designed to exercise different demand
patterns: stable with weekly seasonality, trend up, annual seasonality, intermittent,
trend down, strong weekday pattern, promotion spikes, and a short-history product.
"""

from __future__ import annotations

import io
from datetime import date

import numpy as np
import pandas as pd

SAMPLE_SEED = 42
SAMPLE_START = date(2024, 1, 1)
SAMPLE_END = date(2025, 6, 30)
SAMPLE_FILENAME = "sample_sales.csv"

# product_id, name, category, unit_price, pattern
SAMPLE_PRODUCTS = [
    ("SKU-1001", "Arabica Coffee Beans 1kg", "Beverages", 18.50, "weekly"),
    ("SKU-1002", "Green Tea 100 Bags", "Beverages", 7.25, "trend_up"),
    ("SKU-1003", "Insulated Water Bottle", "Accessories", 24.00, "annual"),
    ("SKU-1004", "Wireless Mouse", "Electronics", 29.99, "intermittent"),
    ("SKU-1005", "USB-C Charger 65W", "Electronics", 39.00, "trend_down"),
    ("SKU-1006", "A5 Notebook", "Stationery", 4.50, "weekday"),
    ("SKU-1007", "LED Desk Lamp", "Home Office", 45.00, "promo"),
    ("SKU-1008", "Seasonal Gift Box", "Gifts", 32.00, "short"),
]


def _expected_demand(pattern: str, days: np.ndarray, dows: np.ndarray, doy: np.ndarray, rng) -> np.ndarray:
    n = len(days)
    t = np.arange(n)
    weekend = (dows >= 5).astype(float)
    if pattern == "weekly":
        return 40 * (1 + 0.35 * weekend)
    if pattern == "trend_up":
        return 10 + 15 * t / n + 2 * weekend
    if pattern == "annual":
        return 12 + 10 * np.clip(np.sin(2 * np.pi * (doy - 80) / 365.25), 0, None)
    if pattern == "intermittent":
        return np.full(n, 0.8)
    if pattern == "trend_down":
        return np.clip(22 - 14 * t / n, 3, None)
    if pattern == "weekday":
        return np.where(dows < 5, 30.0, 4.0)
    if pattern == "promo":
        base = np.full(n, 6.0)
        promo_days = rng.choice(n, size=n // 20, replace=False)
        base[promo_days] *= 3.5
        return base
    if pattern == "short":
        return 9 + 3 * weekend
    raise ValueError(pattern)


def generate_sample_dataframe(seed: int = SAMPLE_SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    all_days = pd.date_range(SAMPLE_START, SAMPLE_END, freq="D")
    rows = []
    for product_id, name, category, price, pattern in SAMPLE_PRODUCTS:
        days = all_days[-40:] if pattern == "short" else all_days
        lam = _expected_demand(
            pattern, days.to_numpy(), days.dayofweek.to_numpy(), days.dayofyear.to_numpy(), rng
        )
        qty = rng.poisson(lam)
        for day, q in zip(days, qty):
            if q == 0:
                continue  # transaction exports have no row for days without sales
            unit_price = round(price * (1 + rng.normal(0, 0.02)), 2)
            # Split some days into two transactions to exercise same-day aggregation.
            if q >= 4 and rng.random() < 0.15:
                first = int(rng.integers(1, q))
                if 2 * first == q:  # keep the two transactions distinguishable
                    first -= 1
                parts = [first, int(q) - first]
            else:
                parts = [int(q)]
            for part in parts:
                rows.append(
                    {
                        "date": day.date().isoformat(),
                        "product_id": product_id,
                        "product_name": name,
                        "category": category,
                        "quantity": part,
                        "unit_price": unit_price,
                    }
                )
    return pd.DataFrame(rows, columns=["date", "product_id", "product_name", "category", "quantity", "unit_price"])


def sample_csv_bytes(seed: int = SAMPLE_SEED) -> bytes:
    buf = io.StringIO()
    generate_sample_dataframe(seed).to_csv(buf, index=False, lineterminator="\n")
    return buf.getvalue().encode("utf-8")

