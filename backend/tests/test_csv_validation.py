from datetime import date

import pytest

from app.errors import PayloadTooLargeError, UnsupportedMediaError, ValidationFailedError
from app.services.csv_validation import normalize_header, validate_sales_csv
from tests.conftest import daily_rows, make_csv

TODAY = date(2026, 1, 1)


def run(raw: bytes, **kw):
    return validate_sales_csv(raw, kw.pop("filename", "sales.csv"), "text/csv", today=TODAY, **kw)


def test_valid_csv_accepts_all_rows():
    raw = make_csv(daily_rows("A", 10, lambda i: i + 1))
    r = run(raw)
    assert r.report["total_rows"] == 10
    assert r.report["accepted_rows"] == 10
    assert r.report["rejected_rows"] == 0
    assert r.report["is_valid"] is True
    assert r.report["product_count"] == 1
    assert len(r.daily) == 10
    assert r.daily["quantity"].sum() == sum(range(1, 11))


def test_header_normalisation_and_aliases():
    assert normalize_header(" Product ID ") == "product_id"
    raw = b"Date,Product ID,Quantity Sold,Unit Price\n2024-01-01,A,5,2.5\n"
    r = run(raw)
    assert r.report["column_mapping"] == {
        "date": "Date",
        "product_id": "Product ID",
        "quantity": "Quantity Sold",
        "unit_price": "Unit Price",
    }
    assert r.products.iloc[0]["unit_price"] == 2.5


def test_missing_required_column():
    with pytest.raises(ValidationFailedError) as exc:
        run(b"date,product_id\n2024-01-01,A\n")
    assert exc.value.code == "missing_required_columns"
    assert exc.value.details["missing"] == ["quantity"]


def test_ambiguous_columns_rejected():
    with pytest.raises(ValidationFailedError) as exc:
        run(b"date,product_id,qty,quantity\n2024-01-01,A,1,2\n")
    assert exc.value.code == "ambiguous_columns"


def test_invalid_dates_rejected_not_guessed():
    raw = b"date,product_id,quantity\n2024-01-01,A,1\n01/02/2024,A,2\nnot-a-date,A,3\n2024-02-30,A,4\n2030-01-01,A,5\n"
    r = run(raw)
    assert r.report["accepted_rows"] == 1
    assert r.report["invalid_dates"] == 4
    assert r.report["future_dates"] == 1
    reasons = {s["row_number"]: s["reasons"] for s in r.report["rejected_samples"]}
    assert reasons[3] == ["invalid date (expected YYYY-MM-DD)"]
    assert reasons[6] == ["date is in the future"]
    assert any("YYYY-MM-DD" in i for i in r.report["instructions"])


def test_non_numeric_and_negative_quantities():
    raw = b"date,product_id,quantity\n2024-01-01,A,abc\n2024-01-02,A,-3\n2024-01-03,A,inf\n2024-01-04,A,\n2024-01-05,A,2.5\n"
    r = run(raw)
    assert r.report["accepted_rows"] == 1
    assert r.report["invalid_quantities"] == 3  # abc, inf, missing
    assert r.report["negative_quantities"] == 1
    assert r.report["missing_values"]["quantity"] == 1
    assert r.daily["quantity"].tolist() == [2.5]


def test_missing_and_invalid_product_ids():
    raw = b"date,product_id,quantity\n2024-01-01,,1\n2024-01-02,bad id!,2\n2024-01-03,OK-1,3\n"
    r = run(raw)
    assert r.report["invalid_product_ids"] == 2
    assert r.report["missing_values"]["product_id"] == 1
    assert r.report["accepted_rows"] == 1


def test_exact_duplicates_excluded_by_default():
    raw = b"date,product_id,quantity\n2024-01-01,A,5\n2024-01-01,A,5\n2024-01-02,A,1\n"
    r = run(raw)
    assert r.report["duplicate_rows"] == 1
    assert r.report["duplicate_row_numbers"] == [3]
    assert r.report["accepted_rows"] == 2
    assert r.daily.set_index("date")["quantity"].to_dict() == {date(2024, 1, 1): 5, date(2024, 1, 2): 1}


def test_duplicate_policy_keep_aggregates_duplicates():
    raw = b"date,product_id,quantity\n2024-01-01,A,5\n2024-01-01,A,5\n"
    r = run(raw, duplicate_policy="keep")
    assert r.report["duplicate_rows"] == 1
    assert r.report["accepted_rows"] == 2
    assert r.daily["quantity"].tolist() == [10]


def test_multiple_transactions_same_day_are_aggregated():
    raw = b"date,product_id,quantity\n2024-01-01,A,5\n2024-01-01,A,3\n2024-01-01,B,1\n"
    r = run(raw)
    assert r.report["duplicate_rows"] == 0
    assert r.report["aggregated_rows"] == 1
    a = r.daily[r.daily.product_id == "A"].iloc[0]
    assert a["quantity"] == 8 and a["transaction_count"] == 2


def test_missing_calendar_dates_reported():
    raw = b"date,product_id,quantity\n2024-01-01,A,1\n2024-01-05,A,1\n2024-01-10,A,1\n"
    r = run(raw)
    summary = r.report["products"][0]
    assert summary["span_days"] == 10
    assert summary["observed_days"] == 3
    assert summary["missing_dates"] == 7
    assert any("treats them as zero-sales days" in w for w in r.report["warnings"])
    # Missing dates are not invented in the validated data itself.
    assert len(r.daily) == 3


def test_empty_file():
    with pytest.raises(ValidationFailedError) as exc:
        run(b"")
    assert exc.value.code == "empty_file"
    with pytest.raises(ValidationFailedError) as exc:
        run(b"date,product_id,quantity\n")
    assert exc.value.code == "empty_file"


def test_malformed_csv():
    with pytest.raises(ValidationFailedError) as exc:
        run(b'date,product_id,quantity\n2024-01-01,A,1,EXTRA,FIELDS\n2024-01-02,"A,2\n')
    assert exc.value.code == "malformed_csv"


def test_unsupported_format_and_binary():
    with pytest.raises(UnsupportedMediaError):
        validate_sales_csv(b"a,b\n1,2\n", "sales.xlsx", "text/csv")
    with pytest.raises(UnsupportedMediaError):
        validate_sales_csv(b"date\x00\x01", "sales.csv", "text/csv")
    with pytest.raises(UnsupportedMediaError):
        validate_sales_csv(b"a\n1\n", "sales.csv", "image/png")


def test_size_and_row_limits():
    raw = make_csv(daily_rows("A", 50, lambda i: 1))
    with pytest.raises(PayloadTooLargeError):
        run(raw, max_bytes=100)
    with pytest.raises(PayloadTooLargeError):
        run(raw, max_rows=10)


def test_invalid_unit_price_is_reported_not_silently_fixed():
    raw = b"date,product_id,quantity,unit_price\n2024-01-01,A,1,abc\n2024-01-02,A,1,3.0\n"
    r = run(raw)
    assert r.report["accepted_rows"] == 2
    assert r.report["invalid_optional_values"] == 1
    assert any("invalid unit_price" in w for w in r.report["warnings"])


def test_no_valid_rows_marks_report_invalid():
    r = run(b"date,product_id,quantity\nbad,A,1\n")
    assert r.report["is_valid"] is False
    assert r.report["accepted_rows"] == 0


def test_coverage_counts_trailing_gap_until_dataset_end():
    raw = b"date,product_id,quantity\n2024-01-01,A,1\n2024-01-02,A,1\n2024-01-01,B,1\n2024-01-05,B,1\n"
    r = run(raw)
    a = next(p for p in r.report["products"] if p["product_id"] == "A")
    assert a["last_date"] == date(2024, 1, 5)
    assert a["missing_dates"] == 3
