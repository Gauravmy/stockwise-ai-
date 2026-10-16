"""Explainable inventory reorder policy (pure calculations, no I/O).

This is a configurable, forecast-driven (s, S) heuristic — not a constrained
optimisation. Definitions (all quantities in demand units):

* lead_time_demand  = sum of forecast demand over the next ``L`` days (L = supplier lead time)
* safety_stock      = safety_stock_quantity, or avg_daily_forecast * safety_stock_days
* reorder_point (s) = lead_time_demand + safety_stock
* protection period = L + coverage_days (time until the *next* order could arrive)
* target_stock (S)  = forecast demand over the protection period + safety_stock
* order_up_to_gap   = max(0, target_stock - current_stock)
* A reorder is recommended when current_stock <= reorder_point. The recommended quantity is
  then the order-up-to gap, raised to the minimum order quantity (if set) and finally rounded
  *up* to a whole number of packs (if a pack size is set). Otherwise it is 0.

Safety stock from "days of cover" is a heuristic; it does not guarantee a statistical
service level.

Stockout risk categories (evaluated in order):
* critical : positive demand and either no stock, or stock runs out before the lead time
             elapses (an order placed today would arrive too late)
* high     : current_stock <= reorder_point (safety stock is being consumed)
* moderate : stock will reach the reorder point within ``MODERATE_WINDOW_DAYS`` days
* low      : otherwise (including products with zero forecast demand)

Overstock: stock covers more than ``overstock_threshold_days`` of average forecast demand,
or there is stock but zero forecast demand.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np

MODERATE_WINDOW_DAYS = 7
RISK_ORDER = {"critical": 0, "high": 1, "moderate": 2, "low": 3}


@dataclass
class InventoryConfig:
    current_stock: float
    supplier_lead_time_days: int
    safety_stock_days: float | None = None
    safety_stock_quantity: float | None = None
    minimum_order_quantity: float | None = None
    order_pack_size: float | None = None
    coverage_days: int = 14
    overstock_threshold_days: int = 90

    def validate(self) -> None:
        if not math.isfinite(self.current_stock) or self.current_stock < 0:
            raise ValueError("current_stock must be a finite number >= 0")
        if not 0 <= self.supplier_lead_time_days <= 365:
            raise ValueError("supplier_lead_time_days must be between 0 and 365")
        if self.safety_stock_days is not None and self.safety_stock_quantity is not None:
            raise ValueError("set either safety_stock_days or safety_stock_quantity, not both")
        if self.safety_stock_days is not None and not 0 <= self.safety_stock_days <= 365:
            raise ValueError("safety_stock_days must be between 0 and 365")
        if self.safety_stock_quantity is not None and self.safety_stock_quantity < 0:
            raise ValueError("safety_stock_quantity must be >= 0")
        if self.minimum_order_quantity is not None and self.minimum_order_quantity < 0:
            raise ValueError("minimum_order_quantity must be >= 0")
        if self.order_pack_size is not None and self.order_pack_size <= 0:
            raise ValueError("order_pack_size must be > 0")
        if not 1 <= self.coverage_days <= 365:
            raise ValueError("coverage_days must be between 1 and 365")
        if not 1 <= self.overstock_threshold_days <= 3650:
            raise ValueError("overstock_threshold_days must be between 1 and 3650")


@dataclass
class Recommendation:
    current_stock: float
    supplier_lead_time_days: int
    avg_daily_forecast: float
    lead_time_demand: float
    safety_stock: float
    safety_stock_method: str
    reorder_point: float
    protection_period_days: int
    protection_period_demand: float
    target_stock: float
    order_up_to_gap: float
    reorder_needed: bool
    recommended_order_quantity: float
    days_until_stockout: float | None
    stockout_within_forecast: bool
    days_of_cover: float | None
    stockout_risk: str
    overstock: bool
    explanation: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def extend_forecast(daily_forecast: list[float], days: int) -> tuple[np.ndarray, bool]:
    """Return at least ``days`` values; pad beyond the horizon with the average daily forecast."""
    f = np.asarray(daily_forecast, dtype=float)
    if f.size == 0:
        raise ValueError("daily_forecast must not be empty")
    if f.size >= days:
        return f, False
    pad = np.full(days - f.size, float(f.mean()))
    return np.concatenate([f, pad]), True


def days_until_stockout(stock: float, daily_forecast: np.ndarray) -> float | None:
    """Fractional day on which cumulative forecast demand first exceeds stock.

    Returns None when stock is not exhausted within the provided forecast (or demand is zero).
    Walking the actual daily forecast handles uneven / highly variable demand correctly.
    """
    if stock <= 0:
        return 0.0 if daily_forecast.sum() > 0 else None
    cumulative = 0.0
    for i, demand in enumerate(daily_forecast):
        if demand > 0 and cumulative + demand > stock:
            return round(i + (stock - cumulative) / demand, 2)
        cumulative += demand
    return None


def apply_order_constraints(
    quantity: float, moq: float | None, pack: float | None
) -> float:
    """Raise to MOQ, then round up to a whole number of packs. 0 stays 0."""
    if quantity <= 0:
        return 0.0
    q = quantity
    if moq:
        q = max(q, moq)
    if pack:
        q = math.ceil(round(q / pack, 9)) * pack
    return float(round(q, 4))


def _fmt(x: float) -> str:
    return f"{x:,.0f}" if abs(x - round(x)) < 1e-9 or abs(x) >= 100 else f"{x:,.1f}"


def recommend(config: InventoryConfig, daily_forecast: list[float]) -> Recommendation:
    config.validate()
    horizon = len(daily_forecast)
    L = int(config.supplier_lead_time_days)
    protection = L + int(config.coverage_days)
    needed = max(protection, horizon)
    f, extrapolated = extend_forecast(daily_forecast, needed)
    warnings: list[str] = []
    if extrapolated:
        warnings.append(
            f"The forecast covers {horizon} days but the lead time plus coverage period is "
            f"{protection} days; days beyond the forecast use the average daily forecast."
        )

    avg_daily = float(np.mean(f[:horizon]))
    lead_time_demand = float(f[:L].sum())
    if config.safety_stock_quantity is not None:
        safety_stock, method = float(config.safety_stock_quantity), "fixed quantity"
    else:
        days = float(config.safety_stock_days or 0.0)
        safety_stock, method = avg_daily * days, f"{_fmt(days)} days of average forecast demand"
    reorder_point = lead_time_demand + safety_stock
    protection_demand = float(f[:protection].sum())
    target_stock = protection_demand + safety_stock
    stock = float(config.current_stock)
    gap = max(0.0, target_stock - stock)
    reorder_needed = stock <= reorder_point and target_stock > 0
    qty = (
        apply_order_constraints(gap, config.minimum_order_quantity, config.order_pack_size)
        if reorder_needed
        else 0.0
    )

    stockout_day = days_until_stockout(stock, f[:horizon])
    days_of_cover = stock / avg_daily if avg_daily > 0 else None

    # --- stockout risk -------------------------------------------------------------
    if avg_daily <= 0 and lead_time_demand <= 0:
        risk = "low"
    elif stock <= 0 or (stockout_day is not None and stockout_day < L):
        risk = "critical"
    elif stock <= reorder_point:
        risk = "high"
    elif stock <= reorder_point + avg_daily * MODERATE_WINDOW_DAYS:
        risk = "moderate"
    else:
        risk = "low"

    overstock = (avg_daily <= 0 and stock > 0) or (
        days_of_cover is not None and days_of_cover > config.overstock_threshold_days
    )

    # --- explanation built from the computed values --------------------------------
    exp: list[str] = []
    exp.append(
        f"Expected demand during the {L}-day supplier lead time is {_fmt(lead_time_demand)} units; "
        f"safety stock is {_fmt(safety_stock)} units ({method}), so the reorder point is "
        f"{_fmt(reorder_point)} units."
    )
    if avg_daily <= 0:
        exp.append("The forecast shows no demand, so no replenishment is recommended.")
    elif reorder_needed:
        exp.append(
            f"Current stock ({_fmt(stock)}) is at or below the reorder point "
            f"({_fmt(reorder_point)}). Replenishment is recommended to reduce the risk of a stockout."
        )
        exp.append(
            f"Target stock covers the lead time plus {config.coverage_days} days of coverage "
            f"({_fmt(protection_demand)} units) plus safety stock = {_fmt(target_stock)} units; "
            f"ordering {_fmt(gap)} units closes the gap."
        )
        if qty != round(gap, 4):
            parts = []
            if config.minimum_order_quantity:
                parts.append(f"minimum order {_fmt(config.minimum_order_quantity)}")
            if config.order_pack_size:
                parts.append(f"pack size {_fmt(config.order_pack_size)}")
            exp.append(
                f"Adjusted to {_fmt(qty)} units to respect the {' and '.join(parts)} (rounded up)."
            )
    else:
        exp.append(
            f"Current stock ({_fmt(stock)}) is above the reorder point ({_fmt(reorder_point)}); "
            "no order is needed yet."
        )
    if stockout_day is not None:
        timing = (
            "before a new order could arrive"
            if stockout_day < L
            else "after the lead time, so an order placed now can arrive in time"
        )
        exp.append(
            f"At forecast demand, stock runs out in about {stockout_day:.1f} days, {timing}."
            if stock > 0
            else "Stock is already exhausted while demand is forecast."
        )
    elif avg_daily > 0:
        exp.append(f"Stock is not expected to run out within the {horizon}-day forecast horizon.")
    if overstock:
        if avg_daily <= 0:
            exp.append("Potential overstock: stock is held but no demand is forecast.")
        else:
            exp.append(
                f"Potential overstock: stock covers about {days_of_cover:.0f} days of forecast "
                f"demand, above the {config.overstock_threshold_days}-day threshold."
            )

    return Recommendation(
        current_stock=stock,
        supplier_lead_time_days=L,
        avg_daily_forecast=round(avg_daily, 4),
        lead_time_demand=round(lead_time_demand, 4),
        safety_stock=round(safety_stock, 4),
        safety_stock_method=method,
        reorder_point=round(reorder_point, 4),
        protection_period_days=protection,
        protection_period_demand=round(protection_demand, 4),
        target_stock=round(target_stock, 4),
        order_up_to_gap=round(gap, 4),
        reorder_needed=reorder_needed,
        recommended_order_quantity=qty,
        days_until_stockout=stockout_day,
        stockout_within_forecast=stockout_day is not None,
        days_of_cover=round(days_of_cover, 2) if days_of_cover is not None else None,
        stockout_risk=risk,
        overstock=overstock,
        explanation=exp,
        warnings=warnings,
    )
