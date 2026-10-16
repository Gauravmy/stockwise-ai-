"""CSV parsing and data-quality validation for historical sales uploads.

This module is pure (no database access) so it can be unit-tested directly.

Policies (also documented in README.md):

* Required columns: ``date``, ``product_id``, ``quantity``. Optional: ``product_name``,
  ``category``, ``unit_price``. Headers are normalised (case, spaces, punctuation) and a
  small explicit alias list is accepted (e.g. "Quantity Sold" -> quantity). If two input
  columns map to the same field the upload is rejected as ambiguous; nothing is guessed.
* Dates must be ISO-8601 ``YYYY-MM-DD``. Ambiguous formats such as ``01/02/2024`` are
  rejected rather than guessed. Dates in the future are rejected.
* Quantities must be finite, non-negative numbers. Invalid values are never replaced —
  the row is rejected and reported.
* Exact duplicate rows (every mapped column identical) are treated as accidental
  double-exports and excluded by default (``duplicate_policy="exclude"``); the first
  occurrence is kept. ``duplicate_policy="keep"`` keeps them (for files where identical
  transactions are legitimate). Non-identical rows for the same product and date are
  legitimate separate transactions and are *aggregated* (summed), never discarded.
* Missing calendar dates inside a product's date range are reported, not filled here.
  The forecasting step treats them as zero-demand days and warns when the share of such
  days is high (see ``app.ml.forecasting``).
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd

from app.errors import PayloadTooLargeError, UnsupportedMediaError, ValidationFailedError
from app.ml.forecasting import MIN_EVALUATION_HISTORY_DAYS, MIN_FORECAST_HISTORY_DAYS

REQUIRED_COLUMNS = ("date", "product_id", "quantity")
OPTIONAL_COLUMNS = ("product_name", "category", "unit_price")

COLUMN_ALIASES: dict[str, set[str]] = {
    "date": {"date", "sale_date", "sales_date", "order_date", "transaction_date"},
    "product_id": {"product_id", "productid", "sku", "product_code", "item_id"},
    "quantity": {"quantity", "qty", "quantity_sold", "units_sold", "units", "sales_quantity"},
    "product_name": {"product_name", "item_name"},
    "category": {"category", "product_category"},
    "unit_price": {"unit_price", "price", "price_per_unit"},
}

ALLOWED_CONTENT_TYPES = {
    "",
    "text/csv",
    "application/csv",
    "text/plain",
    "application/vnd.ms-excel",
    "application/octet-stream",
}

PRODUCT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$")
MAX_REJECTED_SAMPLES = 50
PREVIEW_ROWS = 20
HIGH_MISSING_DATE_RATIO = 0.10

DuplicatePolicy = Literal["exclude", "keep"]


@dataclass
class ValidationResult:
    report: dict
    daily: pd.DataFrame  # columns: product_id, date, quantity, transaction_count
    products: pd.DataFrame  # columns: product_id, name, category, unit_price
    warnings: list[str] = field(default_factory=list)

    @property
    def accepted_rows(self) -> int:
        return int(self.report["accepted_rows"])


def normalize_header(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(header).strip().lower()).strip("_")


def map_columns(headers: list[str]) -> tuple[dict[str, str], list[str]]:
    """Map raw headers to canonical names. Returns (canonical -> raw, ignored headers)."""
    mapping: dict[str, str] = {}
    ignored: list[str] = []
    conflicts: dict[str, list[str]] = {}
    for raw in headers:
        norm = normalize_header(raw)
        canonical = next((c for c, aliases in COLUMN_ALIASES.items() if norm in aliases), None)
        if canonical is None:
            ignored.append(raw)
            continue
        if canonical in mapping:
            conflicts.setdefault(canonical, [mapping[canonical]]).append(raw)
            continue
        mapping[canonical] = raw
    if conflicts:
        detail = "; ".join(f"{k}: {', '.join(v)}" for k, v in conflicts.items())
        raise ValidationFailedError(
            f"Ambiguous columns: several input columns map to the same field ({detail}). "
            "Rename or remove the extra columns so each field appears once.",
            code="ambiguous_columns",
            details={"conflicts": conflicts},
        )
    missing = [c for c in REQUIRED_COLUMNS if c not in mapping]
    if missing:
        raise ValidationFailedError(
            f"Missing required column(s): {', '.join(missing)}.",
            code="missing_required_columns",
            details={
                "missing": missing,
                "found_columns": [str(h) for h in headers],
                "accepted_names": {c: sorted(COLUMN_ALIASES[c]) for c in missing},
            },
        )
    return mapping, ignored


def decode_upload(
    filename: str | None, content_type: str | None, raw: bytes, max_bytes: int
) -> str:
    """File-level checks: extension, content type, size, emptiness, encoding."""
    name = (filename or "").strip()
    if not name.lower().endswith(".csv"):
        raise UnsupportedMediaError(
            "Only .csv files are supported. Export your data as comma-separated values (CSV).",
            details={"filename": name[:255]},
        )
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype not in ALLOWED_CONTENT_TYPES:
        raise UnsupportedMediaError(
            f"Unsupported content type '{ctype}'. Upload a CSV file.",
            details={"content_type": ctype},
        )
    if len(raw) > max_bytes:
        raise PayloadTooLargeError(
            f"File exceeds the maximum upload size of {max_bytes // (1024 * 1024)} MB.",
            details={"max_bytes": max_bytes},
        )
    if not raw.strip():
        raise ValidationFailedError("The uploaded file is empty.", code="empty_file")
    if b"\x00" in raw[:8192]:
        raise UnsupportedMediaError("The file appears to be binary, not a text CSV file.")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationFailedError(
            "The file is not valid UTF-8 text. Re-save the CSV with UTF-8 encoding.",
            code="invalid_encoding",
        ) from exc


def parse_csv(text: str, max_rows: int) -> pd.DataFrame:
    try:
        df = pd.read_csv(
            io.StringIO(text),
            dtype=str,
            keep_default_na=False,
            skipinitialspace=True,
            on_bad_lines="error",
            engine="python",
        )
    except pd.errors.EmptyDataError as exc:
        raise ValidationFailedError("The CSV file has no header or data.", code="empty_file") from exc
    except (pd.errors.ParserError, csv.Error) as exc:
        raise ValidationFailedError(
            "The CSV file is malformed and could not be parsed. Check for rows with a "
            "different number of fields than the header and for unbalanced quotes.",
            code="malformed_csv",
            details={"parser_message": str(exc).splitlines()[0][:300]},
        ) from exc
    if df.shape[0] == 0:
        raise ValidationFailedError(
            "The CSV file has a header but no data rows.", code="empty_file"
        )
    if df.shape[0] > max_rows:
        raise PayloadTooLargeError(
            f"The file has {df.shape[0]} data rows; the maximum is {max_rows}.",
            details={"max_rows": max_rows, "rows": int(df.shape[0])},
        )
    return df


def _to_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.str.replace(",", "", regex=False), errors="coerce")


def validate_sales_csv(
    raw: bytes,
    filename: str | None,
    content_type: str | None = "text/csv",
    *,
    max_bytes: int = 5 * 1024 * 1024,
    max_rows: int = 200_000,
    duplicate_policy: DuplicatePolicy = "exclude",
    today: date | None = None,
) -> ValidationResult:
    """Validate an uploaded CSV and return a report plus the cleaned, aggregated data.

    Raises ``AppError`` subclasses for file-level problems (wrong format, too large,
    malformed, missing required columns). Row-level problems never raise: rows are
    rejected and explained in the report.
    """
    if duplicate_policy not in ("exclude", "keep"):
        raise ValidationFailedError("duplicate_policy must be 'exclude' or 'keep'.")
    today = today or date.today()
    text = decode_upload(filename, content_type, raw, max_bytes)
    df = parse_csv(text, max_rows)
    mapping, ignored = map_columns(list(df.columns))

    data = pd.DataFrame({c: df[raw_col].astype(str).str.strip() for c, raw_col in mapping.items()})
    for col in OPTIONAL_COLUMNS:
        if col not in data:
            data[col] = ""
    total_rows = int(len(data))
    row_numbers = pd.Series(np.arange(total_rows) + 2, index=data.index)  # +1 header, +1 base-1

    reasons: dict[int, list[str]] = {}

    def flag(mask: pd.Series, reason: str) -> None:
        for idx in data.index[mask]:
            reasons.setdefault(int(idx), []).append(reason)

    missing_values = {c: int((data[c] == "").sum()) for c in REQUIRED_COLUMNS}
    missing_values.update({c: int((data[c] == "").sum()) for c in OPTIONAL_COLUMNS if c in mapping})

    # --- product_id -----------------------------------------------------------------
    pid_missing = data["product_id"] == ""
    pid_invalid = ~pid_missing & ~data["product_id"].str.match(PRODUCT_ID_PATTERN)
    flag(pid_missing, "missing product_id")
    flag(pid_invalid, "invalid product_id (use 1-64 letters, digits, '-', '_' or '.')")

    # --- date -----------------------------------------------------------------------
    date_missing = data["date"] == ""
    parsed_dates = pd.to_datetime(data["date"], format="%Y-%m-%d", errors="coerce")
    date_invalid = ~date_missing & parsed_dates.isna()
    date_future = parsed_dates.notna() & (parsed_dates > pd.Timestamp(today))
    flag(date_missing, "missing date")
    flag(date_invalid, "invalid date (expected YYYY-MM-DD)")
    flag(date_future, "date is in the future")

    # --- quantity -------------------------------------------------------------------
    qty_missing = data["quantity"] == ""
    qty = _to_float(data["quantity"])
    qty_non_numeric = ~qty_missing & qty.isna()
    qty_non_finite = qty.notna() & ~np.isfinite(qty)
    qty_negative = np.isfinite(qty) & (qty < 0)
    flag(qty_missing, "missing quantity")
    flag(qty_non_numeric, "quantity is not a number")
    flag(qty_non_finite, "quantity is not a finite number")
    flag(qty_negative, "negative quantity (returns/adjustments are not supported)")

    # --- optional unit_price (invalid values are nulled and reported, row kept) ------
    price = _to_float(data["unit_price"])
    price_bad = (data["unit_price"] != "") & (~np.isfinite(price) | (price < 0))
    invalid_optional = int(price_bad.sum())
    price = price.where(~price_bad)

    rejected_idx = sorted(reasons)
    rejected_mask = data.index.isin(rejected_idx)
    valid = data.loc[~rejected_mask].copy()
    valid["date"] = parsed_dates.loc[~rejected_mask].dt.date
    valid["quantity"] = qty.loc[~rejected_mask].astype(float)
    valid["unit_price"] = price.loc[~rejected_mask]
    valid["row_number"] = row_numbers.loc[~rejected_mask]

    # --- duplicates -----------------------------------------------------------------
    dup_cols = ["date", "product_id", "quantity", "product_name", "category", "unit_price"]
    dup_mask = valid.duplicated(subset=dup_cols, keep="first")
    duplicate_rows = int(dup_mask.sum())
    duplicate_row_numbers = valid.loc[dup_mask, "row_number"].astype(int).tolist()[:MAX_REJECTED_SAMPLES]
    if duplicate_policy == "exclude":
        accepted = valid.loc[~dup_mask].copy()
    else:
        accepted = valid.copy()

    warnings: list[str] = []
    instructions: list[str] = []

    if ignored:
        warnings.append(f"Ignored unrecognised column(s): {', '.join(map(str, ignored))}.")
    if invalid_optional:
        warnings.append(
            f"{invalid_optional} row(s) had an invalid unit_price; the price was left empty "
            "for those rows (the sales quantity was still accepted)."
        )
    if duplicate_rows:
        if duplicate_policy == "exclude":
            warnings.append(
                f"{duplicate_rows} exact duplicate row(s) were excluded (first occurrence kept)."
            )
        else:
            warnings.append(
                f"{duplicate_rows} exact duplicate row(s) were kept and aggregated because "
                "duplicate_policy='keep'."
            )

    # --- aggregation ----------------------------------------------------------------
    if len(accepted):
        daily = (
            accepted.groupby(["product_id", "date"], as_index=False)
            .agg(quantity=("quantity", "sum"), transaction_count=("quantity", "size"))
            .sort_values(["product_id", "date"])
            .reset_index(drop=True)
        )
    else:
        daily = pd.DataFrame(columns=["product_id", "date", "quantity", "transaction_count"])
    aggregated_rows = int(len(accepted) - len(daily))
    if aggregated_rows:
        warnings.append(
            f"{aggregated_rows} row(s) were additional transactions for a product/date that "
            "already had a row; they were summed into daily totals."
        )

    # --- products -------------------------------------------------------------------
    product_rows = []
    for pid, group in accepted.groupby("product_id"):
        names = group.loc[group["product_name"] != "", "product_name"]
        cats = group.loc[group["category"] != "", "category"]
        if names.nunique() > 1:
            warnings.append(
                f"Product {pid} has {names.nunique()} different names; the most frequent is used."
            )
        product_rows.append(
            {
                "product_id": pid,
                "name": names.mode().iloc[0][:200] if len(names) else None,
                "category": cats.mode().iloc[0][:100] if len(cats) else None,
                "unit_price": float(group["unit_price"].median())
                if group["unit_price"].notna().any()
                else None,
            }
        )
    products = pd.DataFrame(product_rows, columns=["product_id", "name", "category", "unit_price"])

    # --- per-product coverage / missing dates ---------------------------------------
    product_summaries = []
    dataset_end = max(daily["date"]) if len(daily) else None
    for pid, group in daily.groupby("product_id"):
        # Coverage runs to the dataset end: trailing days without rows count as missing.
        start, end = min(group["date"]), dataset_end
        span = (end - start).days + 1
        observed = int(group["date"].nunique())
        missing = span - observed
        ratio = missing / span if span else 0.0
        product_summaries.append(
            {
                "product_id": pid,
                "first_date": start,
                "last_date": end,
                "span_days": span,
                "observed_days": observed,
                "missing_dates": missing,
                "missing_date_ratio": round(ratio, 4),
                "total_quantity": float(group["quantity"].sum()),
            }
        )
        if ratio > HIGH_MISSING_DATE_RATIO:
            warnings.append(
                f"Product {pid}: {missing} of {span} calendar days ({ratio:.0%}) have no rows. "
                "Forecasting treats them as zero-sales days; if they are data gaps rather than "
                "days without sales, forecasts may be understated."
            )
        if span < MIN_FORECAST_HISTORY_DAYS:
            warnings.append(
                f"Product {pid}: only {span} day(s) of history; at least "
                f"{MIN_FORECAST_HISTORY_DAYS} are needed for any forecast."
            )
        elif span < MIN_EVALUATION_HISTORY_DAYS:
            warnings.append(
                f"Product {pid}: {span} days of history; at least {MIN_EVALUATION_HISTORY_DAYS} "
                "are needed for a validated (holdout-evaluated) forecast."
            )

    # --- rejected samples -----------------------------------------------------------
    rejected_samples = [
        {
            "row_number": int(row_numbers.loc[idx]),
            "reasons": reasons[idx],
            "values": {c: str(data.at[idx, c])[:50] for c in mapping},
        }
        for idx in rejected_idx[:MAX_REJECTED_SAMPLES]
    ]

    counts = {
        "invalid_dates": int((date_missing | date_invalid | date_future).sum()),
        "future_dates": int(date_future.sum()),
        "invalid_quantities": int((qty_missing | qty_non_numeric | qty_non_finite).sum()),
        "negative_quantities": int(qty_negative.sum()),
        "invalid_product_ids": int((pid_missing | pid_invalid).sum()),
    }
    if counts["invalid_dates"]:
        instructions.append("Use ISO dates in the form YYYY-MM-DD (e.g. 2025-03-31) and remove future dates.")
    if counts["invalid_quantities"]:
        instructions.append("Make sure every quantity is a plain number such as 12 or 3.5.")
    if counts["negative_quantities"]:
        instructions.append(
            "Remove negative quantities (returns or stock adjustments) or net them into the sale day's total."
        )
    if counts["invalid_product_ids"]:
        instructions.append("Give every row a product_id made of letters, digits, '-', '_' or '.'.")
    if duplicate_rows and duplicate_policy == "exclude":
        instructions.append(
            "If identical rows are genuine separate transactions, re-upload with duplicate_policy=keep."
        )

    accepted_rows = int(len(accepted))
    if accepted_rows == 0:
        instructions.append("No rows passed validation; fix the issues above and upload again.")

    report = {
        "filename": (filename or "")[:255],
        "is_valid": accepted_rows > 0,
        "total_rows": total_rows,
        "accepted_rows": accepted_rows,
        "rejected_rows": len(rejected_idx),
        "duplicate_rows": duplicate_rows,
        "duplicate_row_numbers": duplicate_row_numbers,
        "duplicate_policy": duplicate_policy,
        "aggregated_rows": aggregated_rows,
        "daily_records": int(len(daily)),
        "product_count": int(daily["product_id"].nunique()) if len(daily) else 0,
        "date_start": min(daily["date"]) if len(daily) else None,
        "date_end": max(daily["date"]) if len(daily) else None,
        "missing_values": missing_values,
        "invalid_optional_values": invalid_optional,
        **counts,
        "column_mapping": mapping,
        "ignored_columns": [str(c) for c in ignored],
        "products": product_summaries,
        "rejected_samples": rejected_samples,
        "warnings": warnings,
        "instructions": instructions,
        "preview": [
            {
                "row_number": int(r.row_number),
                "date": r.date,
                "product_id": r.product_id,
                "quantity": float(r.quantity),
                "product_name": r.product_name or None,
                "category": r.category or None,
                "unit_price": None if pd.isna(r.unit_price) else float(r.unit_price),
            }
            for r in accepted.head(PREVIEW_ROWS).itertuples()
        ],
    }
    return ValidationResult(report=report, daily=daily, products=products, warnings=warnings)
