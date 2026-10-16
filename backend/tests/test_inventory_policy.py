import pytest

from app.services.inventory_policy import (
    InventoryConfig,
    apply_order_constraints,
    days_until_stockout,
    recommend,
)

import numpy as np


def cfg(**kw):
    base = dict(current_stock=100, supplier_lead_time_days=5, coverage_days=10)
    base.update(kw)
    return InventoryConfig(**base)


FLAT_10 = [10.0] * 30


def test_reorder_point_is_lead_time_demand_plus_safety_stock():
    r = recommend(cfg(safety_stock_days=2), FLAT_10)
    assert r.lead_time_demand == 50
    assert r.safety_stock == 20
    assert r.reorder_point == 70


def test_fixed_safety_stock_quantity():
    r = recommend(cfg(safety_stock_quantity=33), FLAT_10)
    assert r.safety_stock == 33
    assert r.safety_stock_method == "fixed quantity"


def test_target_stock_and_reorder_quantity_when_below_reorder_point():
    r = recommend(cfg(current_stock=40, safety_stock_days=2), FLAT_10)
    # protection = 5 + 10 days -> 150 demand; target = 150 + 20
    assert r.target_stock == 170
    assert r.reorder_needed
    assert r.recommended_order_quantity == 130
    assert r.target_stock != r.reorder_point  # the two are distinct concepts


def test_sufficient_stock_needs_no_order():
    r = recommend(cfg(current_stock=500, safety_stock_days=2), FLAT_10)
    assert not r.reorder_needed
    assert r.recommended_order_quantity == 0
    assert r.stockout_risk == "low"
    assert any("no order is needed" in e for e in r.explanation)


def test_zero_stock_is_critical():
    r = recommend(cfg(current_stock=0), FLAT_10)
    assert r.stockout_risk == "critical"
    assert r.days_until_stockout == 0
    assert r.reorder_needed


def test_stockout_before_lead_time_is_critical():
    r = recommend(cfg(current_stock=30, supplier_lead_time_days=5), FLAT_10)
    assert r.days_until_stockout == pytest.approx(3.0)
    assert r.stockout_risk == "critical"
    assert any("before a new order could arrive" in e for e in r.explanation)


def test_high_and_moderate_risk_rules():
    # ROP = 50 (no safety stock); stock 60 > ROP but within 7 days of demand -> moderate
    assert recommend(cfg(current_stock=60), FLAT_10).stockout_risk == "moderate"
    # stock == ROP, stockout at day 5 == lead time (not before) -> high
    assert recommend(cfg(current_stock=50), FLAT_10).stockout_risk == "high"


def test_zero_lead_time():
    r = recommend(cfg(current_stock=5, supplier_lead_time_days=0), FLAT_10)
    assert r.lead_time_demand == 0
    assert r.reorder_point == 0
    assert not r.reorder_needed  # stock 5 > reorder point 0
    r0 = recommend(cfg(current_stock=0, supplier_lead_time_days=0), FLAT_10)
    assert r0.reorder_needed and r0.stockout_risk == "critical"


def test_minimum_order_quantity_and_pack_rounding():
    assert apply_order_constraints(13, moq=50, pack=None) == 50
    assert apply_order_constraints(13, moq=None, pack=12) == 24
    assert apply_order_constraints(51, moq=50, pack=25) == 75
    assert apply_order_constraints(48, moq=None, pack=12) == 48  # exact multiple stays
    assert apply_order_constraints(0, moq=50, pack=25) == 0
    r = recommend(cfg(current_stock=40, minimum_order_quantity=200, order_pack_size=24), FLAT_10)
    assert r.order_up_to_gap == 110
    assert r.recommended_order_quantity == 216  # max(110, 200) -> ceil(200/24)*24


def test_zero_demand_is_low_risk_and_overstock_if_stock_held():
    r = recommend(cfg(current_stock=10), [0.0] * 30)
    assert r.stockout_risk == "low"
    assert r.recommended_order_quantity == 0
    assert r.days_until_stockout is None
    assert r.overstock
    r_empty = recommend(cfg(current_stock=0), [0.0] * 30)
    assert not r_empty.overstock and not r_empty.reorder_needed


def test_overstock_uses_coverage_relative_to_demand():
    # 1000 units at 10/day = 100 days > 90-day threshold
    assert recommend(cfg(current_stock=1000), FLAT_10).overstock
    # same absolute stock with much higher demand is not overstock
    assert not recommend(cfg(current_stock=1000), [100.0] * 30).overstock
    assert not recommend(cfg(current_stock=1000, overstock_threshold_days=120), FLAT_10).overstock


def test_variable_demand_stockout_walks_daily_forecast():
    f = np.array([0, 0, 50, 0, 0, 50], dtype=float)
    assert days_until_stockout(60, f) == pytest.approx(5.2)
    assert days_until_stockout(100, f) is None


def test_short_forecast_is_extended_with_warning():
    r = recommend(cfg(current_stock=10, supplier_lead_time_days=10, coverage_days=10), [10.0] * 7)
    assert r.protection_period_demand == 200
    assert r.warnings


@pytest.mark.parametrize(
    "kw",
    [
        dict(current_stock=-1),
        dict(supplier_lead_time_days=-1),
        dict(supplier_lead_time_days=400),
        dict(safety_stock_days=2, safety_stock_quantity=3),
        dict(safety_stock_quantity=-5),
        dict(order_pack_size=0),
        dict(coverage_days=0),
        dict(current_stock=float("nan")),
    ],
)
def test_invalid_configuration_rejected(kw):
    with pytest.raises(ValueError):
        recommend(cfg(**kw), FLAT_10)


def test_explanation_reflects_computed_values():
    r = recommend(cfg(current_stock=40, safety_stock_days=2), FLAT_10)
    text = " ".join(r.explanation)
    assert "reorder point is 70" in text
    assert "Current stock (40)" in text
    assert "Replenishment is recommended" in text
