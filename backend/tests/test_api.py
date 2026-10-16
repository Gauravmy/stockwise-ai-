from datetime import date, timedelta

import pytest

from tests.conftest import daily_rows, make_csv

API = "/api/v1"
P2_START = date(2024, 1, 1) + timedelta(days=90)


def upload(client, raw: bytes, name="sales.csv", **params):
    return client.post(f"{API}/datasets/upload", files={"file": (name, raw, "text/csv")}, params=params)


def weekly_csv(product="P1", days=120):
    return make_csv(daily_rows(product, days, lambda i: 20 if i % 7 < 5 else 4))


@pytest.fixture
def loaded(client):
    raw = make_csv(
        daily_rows("P1", 120, lambda i: 20 if i % 7 < 5 else 4)
        + daily_rows("P2", 30, lambda i: 3, start=P2_START)  # new product: last 30 days only
    )
    r = upload(client, raw)
    assert r.status_code == 201, r.text
    return r.json()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "X-Request-ID" in r.headers


def test_openapi_lists_core_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    for p in [
        "/api/v1/products", "/api/v1/products/{product_id}", "/api/v1/datasets/upload",
        "/api/v1/datasets", "/api/v1/datasets/{dataset_id}", "/api/v1/forecasts",
        "/api/v1/forecasts/{forecast_id}", "/api/v1/inventory", "/api/v1/inventory/{product_id}",
        "/api/v1/inventory/recommendations", "/api/v1/dashboard/summary",
    ]:
        assert p in paths


def test_upload_success_creates_active_dataset(client, loaded):
    ds = loaded["dataset"]
    assert ds["is_active"] and ds["accepted_rows"] == 150 and ds["product_count"] == 2
    assert loaded["report"]["total_rows"] == 150
    listing = client.get(f"{API}/datasets").json()
    assert listing["total"] == 1
    detail = client.get(f"{API}/datasets/{ds['id']}").json()
    assert detail["validation_report"]["accepted_rows"] == 150


def test_validate_endpoint_does_not_persist(client):
    r = client.post(f"{API}/datasets/validate", files={"file": ("s.csv", weekly_csv(), "text/csv")})
    assert r.status_code == 200
    assert r.json()["report"]["accepted_rows"] == 120
    assert len(r.json()["report"]["preview"]) == 20
    assert client.get(f"{API}/datasets").json()["total"] == 0


def test_upload_failures(client):
    r = upload(client, b"date,product_id\n2024-01-01,A\n")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "missing_required_columns"

    r = upload(client, b"date,product_id,quantity\nbad,A,1\n")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "no_valid_rows"

    r = upload(client, b"x", name="sales.json")
    assert r.status_code == 415

    r = upload(client, b"")
    assert r.status_code == 422 and r.json()["error"]["code"] == "empty_file"


def test_duplicate_import_rejected(client, loaded):
    raw = make_csv(
        daily_rows("P1", 120, lambda i: 20 if i % 7 < 5 else 4)
        + daily_rows("P2", 30, lambda i: 3, start=P2_START)
    )
    r = upload(client, raw)
    assert r.status_code == 409
    assert r.json()["error"]["details"]["dataset_id"] == loaded["dataset"]["id"]


def test_new_upload_becomes_active_version(client, loaded):
    r = upload(client, make_csv(daily_rows("P3", 60, lambda i: 1)), name="v2.csv")
    assert r.status_code == 201
    products = client.get(f"{API}/products").json()
    assert [p["product_id"] for p in products["items"]] == ["P3"]
    # Re-activate the first version
    r = client.post(f"{API}/datasets/{loaded['dataset']['id']}/activate")
    assert r.status_code == 200 and r.json()["is_active"]
    ids = [p["product_id"] for p in client.get(f"{API}/products").json()["items"]]
    assert ids == ["P1", "P2"]


def test_products_list_detail_and_filters(client, loaded):
    r = client.get(f"{API}/products", params={"search": "p1"})
    assert [p["product_id"] for p in r.json()["items"]] == ["P1"]
    detail = client.get(f"{API}/products/P1", params={"start_date": "2024-01-10", "end_date": "2024-01-12"}).json()
    assert [s["date"] for s in detail["sales"]] == ["2024-01-10", "2024-01-11", "2024-01-12"]
    assert detail["history_days"] == 120
    assert client.get(f"{API}/products/NOPE").status_code == 404
    bad = client.get(f"{API}/products/P1", params={"start_date": "2024-02-01", "end_date": "2024-01-01"})
    assert bad.status_code == 422


def test_forecast_creation_and_persistence(client, loaded):
    r = client.post(f"{API}/forecasts", json={"product_id": "P1", "horizon_days": 14})
    assert r.status_code == 201, r.text
    run = r.json()
    assert len(run["points"]) == 14
    assert run["confidence"] == "validated"
    assert run["total_forecast"] == pytest.approx(sum(p["predicted_quantity"] for p in run["points"]))
    evals = {e["model_name"]: e for e in run["evaluations"]}
    assert set(evals) == {"moving_average", "seasonal_naive", "random_forest"}
    assert sum(e["is_selected"] for e in evals.values()) == 1
    assert evals[run["selected_model"]]["mae"] == min(e["mae"] for e in evals.values())
    assert all(len(e["holdout"]) == e["test_samples"] for e in evals.values())

    fetched = client.get(f"{API}/forecasts/{run['id']}").json()
    assert fetched["points"] == run["points"]
    listing = client.get(f"{API}/forecasts", params={"product_id": "P1"}).json()
    assert listing["total"] == 1 and listing["items"][0]["id"] == run["id"]


def test_forecast_low_confidence_for_short_history(client, loaded):
    run = client.post(f"{API}/forecasts", json={"product_id": "P2", "horizon_days": 7}).json()
    assert run["confidence"] == "low"
    assert all(e["mae"] is None for e in run["evaluations"])


def test_forecast_invalid_requests(client, loaded):
    assert client.post(f"{API}/forecasts", json={"product_id": "P1", "horizon_days": 0}).status_code == 422
    assert client.post(f"{API}/forecasts", json={"horizon_days": 7}).status_code == 422
    assert client.post(f"{API}/forecasts", json={"product_id": "NOPE"}).status_code == 404
    assert client.get(f"{API}/forecasts/9999").status_code == 404


def test_forecast_without_dataset(client):
    r = client.post(f"{API}/forecasts", json={"product_id": "P1", "horizon_days": 7})
    assert r.status_code in (404, 422)


def test_batch_forecast(client, loaded):
    r = client.post(f"{API}/forecasts/batch", json={"horizon_days": 7})
    assert r.status_code == 201
    assert {c["product_id"] for c in r.json()["created"]} == {"P1", "P2"}


INV = {"current_stock": 30, "supplier_lead_time_days": 5, "safety_stock_days": 2}


def test_inventory_create_update_and_recommendations(client, loaded):
    r = client.post(f"{API}/inventory", json={"product_id": "P1", **INV})
    assert r.status_code == 201, r.text
    assert client.post(f"{API}/inventory", json={"product_id": "P1", **INV}).status_code == 409

    recs = client.get(f"{API}/inventory/recommendations").json()
    p1 = next(x for x in recs if x["product_id"] == "P1")
    assert p1["status"] == "no_forecast"
    p2 = next(x for x in recs if x["product_id"] == "P2")
    assert p2["status"] == "not_configured"

    client.post(f"{API}/forecasts", json={"product_id": "P1", "horizon_days": 30})
    recs = client.get(f"{API}/inventory/recommendations").json()
    p1 = next(x for x in recs if x["product_id"] == "P1")
    rec = p1["recommendation"]
    assert p1["status"] == "ok"
    assert rec["reorder_point"] == pytest.approx(rec["lead_time_demand"] + rec["safety_stock"], abs=1e-3)
    assert rec["reorder_needed"] and rec["recommended_order_quantity"] > 0
    assert rec["stockout_risk"] == "critical"

    r = client.put(f"{API}/inventory/P1", json={**INV, "current_stock": 5000})
    assert r.status_code == 200 and r.json()["current_stock"] == 5000
    rec = next(x for x in client.get(f"{API}/inventory/recommendations").json() if x["product_id"] == "P1")
    assert rec["recommendation"]["recommended_order_quantity"] == 0
    assert rec["recommendation"]["overstock"] is True
    assert client.get(f"{API}/inventory").json()[0]["current_stock"] == 5000

    filtered = client.get(f"{API}/inventory/recommendations", params={"risk": "low"}).json()
    assert all(x["recommendation"]["stockout_risk"] == "low" for x in filtered)


def test_inventory_validation_and_missing(client, loaded):
    bad = client.post(f"{API}/inventory", json={"product_id": "P1", "current_stock": -1, "supplier_lead_time_days": 3})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "invalid_request"
    both = client.post(
        f"{API}/inventory",
        json={"product_id": "P1", **INV, "safety_stock_quantity": 4},
    )
    assert both.status_code == 422
    assert client.put(f"{API}/inventory/P1", json=INV).status_code == 404
    assert client.post(f"{API}/inventory", json={"product_id": "NOPE", **INV}).status_code == 404


def test_dashboard_and_insights(client, loaded):
    client.post(f"{API}/inventory", json={"product_id": "P1", **INV})
    client.post(f"{API}/forecasts", json={"product_id": "P1", "horizon_days": 30})
    d = client.get(f"{API}/dashboard/summary", params={"period_days": 7}).json()
    assert d["total_products"] == 2
    assert d["products_at_risk"] == 1
    assert d["products_requiring_reorder"] == 1
    run = client.get(f"{API}/forecasts").json()["items"][0]
    full = client.get(f"{API}/forecasts/{run['id']}").json()
    assert d["forecast_demand"] == pytest.approx(sum(p["predicted_quantity"] for p in full["points"][:7]), abs=0.01)
    assert any(s["forecast"] is not None for s in d["demand_series"])
    ins = client.get(f"{API}/insights").json()
    assert {t["product_id"] for t in ins["trends"]} == {"P1", "P2"}
    assert ins["reorder_priorities"][0]["product_id"] == "P1"


def test_sample_download_and_load(client):
    r = client.get(f"{API}/datasets/sample")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.content.startswith(b"date,product_id")
    r = client.post(f"{API}/datasets/sample/load")
    assert r.status_code == 201
    assert r.json()["dataset"]["is_synthetic"] is True
    assert client.post(f"{API}/datasets/sample/load").status_code == 409


def test_errors_never_leak_stack_traces(client, monkeypatch):
    from app.services import analytics

    def boom(*a, **k):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(analytics, "dashboard_summary", boom)
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        from app.db.session import get_db
        app.dependency_overrides[get_db] = client.app.dependency_overrides[get_db]
        r = c.get(f"{API}/dashboard/summary")
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "internal_error"
    assert "secret" not in r.text and "Traceback" not in r.text


def test_unknown_route_structured_404(client):
    r = client.get(f"{API}/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_dates_serialised_iso(client, loaded):
    p = client.get(f"{API}/products/P1").json()
    assert p["first_date"] == date(2024, 1, 1).isoformat()
