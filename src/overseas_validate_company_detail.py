#!/usr/bin/env python3
"""Create and validate long-format data used by overseas company detail pages."""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path


FIELDS = [
    "company",
    "section",
    "period_role",
    "dimension",
    "metric",
    "metric_type",
    "period_current",
    "value_current",
    "period_compare",
    "value_compare",
    "currency",
    "unit",
    "source_current",
    "source_compare",
    "notes",
]

SECTIONS = {"h1_summary", "quarter", "business_module"}
PERIOD_ROLES = {"H1", "Q1", "Q2", "Q3", "Q4", "FY"}
METRIC_TYPES = {"amount", "stock", "rate", "per_share"}
EXPECTED_UNITS = {
    "amount": "currency_K",
    "stock": "currency_K",
    "rate": "percent",
    "per_share": "currency_per_share",
}


def decimal_or_none(value: str) -> Decimal | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    return Decimal(text)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def validate_rows(rows: list[dict[str, str]], tolerance: Decimal = Decimal("1")) -> list[str]:
    errors: list[str] = []
    required_text = ["company", "section", "period_role", "dimension", "metric", "metric_type", "period_current"]

    for number, row in enumerate(rows, 2):
        missing = [field for field in required_text if not str(row.get(field, "")).strip()]
        if missing:
            errors.append(f"row {number}: missing {', '.join(missing)}")
            continue

        section = row["section"].strip()
        period_role = row["period_role"].strip()
        metric_type = row["metric_type"].strip()
        unit = row.get("unit", "").strip()
        currency = row.get("currency", "").strip()

        if section not in SECTIONS:
            errors.append(f"row {number}: unsupported section {section}")
        if period_role not in PERIOD_ROLES:
            errors.append(f"row {number}: unsupported period_role {period_role}")
        if metric_type not in METRIC_TYPES:
            errors.append(f"row {number}: unsupported metric_type {metric_type}")
            continue
        if unit != EXPECTED_UNITS[metric_type]:
            errors.append(f"row {number}: {metric_type} must use {EXPECTED_UNITS[metric_type]}")
        if metric_type in {"amount", "stock", "per_share"} and not currency:
            errors.append(f"row {number}: currency is required for {metric_type}")
        if section == "h1_summary" and period_role != "H1":
            errors.append(f"row {number}: h1_summary must use period_role H1")
        if section == "quarter" and period_role not in {"Q1", "Q2", "Q3", "Q4"}:
            errors.append(f"row {number}: quarter section must use a quarter period_role")

        try:
            current = decimal_or_none(row.get("value_current", ""))
            compare = decimal_or_none(row.get("value_compare", ""))
        except InvalidOperation:
            errors.append(f"row {number}: values must be numeric or blank")
            continue

        notes = row.get("notes", "")
        if current is None and "未披露" not in notes:
            errors.append(f"row {number}: blank current value must be marked 未披露 in notes")
        if current is not None and not row.get("source_current", "").strip():
            errors.append(f"row {number}: populated current value requires source_current")
        if compare is not None and not row.get("source_compare", "").strip():
            errors.append(f"row {number}: populated compare value requires source_compare")

    errors.extend(reconcile_h1(rows, tolerance))
    return errors


def reconcile_h1(rows: list[dict[str, str]], tolerance: Decimal) -> list[str]:
    errors: list[str] = []
    groups: dict[tuple[str, str, str, str], dict[str, dict[str, str]]] = {}
    for row in rows:
        if row.get("metric_type") != "amount" or row.get("section") not in {"h1_summary", "quarter"}:
            continue
        key = (
            row.get("company", ""),
            row.get("dimension", ""),
            row.get("metric", ""),
            row.get("currency", ""),
        )
        groups.setdefault(key, {})[row.get("period_role", "")] = row

    for key, periods in groups.items():
        if not {"H1", "Q1", "Q2"}.issubset(periods):
            continue
        h1, q1, q2 = periods["H1"], periods["Q1"], periods["Q2"]
        for value_field, label in (("value_current", "current"), ("value_compare", "compare")):
            try:
                values = [decimal_or_none(item.get(value_field, "")) for item in (h1, q1, q2)]
            except InvalidOperation:
                continue
            if any(value is None for value in values):
                continue
            h1_value, q1_value, q2_value = values
            assert h1_value is not None and q1_value is not None and q2_value is not None
            delta = h1_value - q1_value - q2_value
            if abs(delta) > tolerance:
                company, dimension, metric, currency = key
                errors.append(
                    f"reconciliation: {company}/{dimension}/{metric}/{label} H1 != Q1+Q2 "
                    f"({delta:+} {currency} K)"
                )
    return errors


def write_template(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    source = "https://investor.ti.com/..."
    rows = [
        ["TI", "h1_summary", "H1", "consolidated", "revenue", "amount", "2026 H1", "8691000", "2025 H1", "8223000", "USD", "currency_K", source, source, ""],
        ["TI", "h1_summary", "H1", "consolidated", "gross_margin", "rate", "2026 H1", "58.0", "2025 H1", "57.2", "", "percent", source, source, "compare in percentage points"],
        ["TI", "quarter", "Q1", "consolidated", "revenue", "amount", "2026 Q1", "4070000", "2025 Q1", "4003000", "USD", "currency_K", source, source, ""],
        ["TI", "quarter", "Q2", "consolidated", "revenue", "amount", "2026 Q2", "4621000", "2025 Q2", "4220000", "USD", "currency_K", source, source, ""],
        ["TI", "business_module", "Q2", "Analog", "revenue", "amount", "2026 Q2", "3600000", "2025 Q2", "3300000", "USD", "currency_K", source, source, "official segment definition"],
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(FIELDS)
        writer.writerows(rows)
    print(f"Wrote company detail template to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--write-template", type=Path)
    parser.add_argument("--tolerance", default="1", help="H1 reconciliation tolerance in local-currency K")
    args = parser.parse_args()

    if args.write_template:
        write_template(args.write_template)
        return
    if not args.input:
        raise SystemExit("--input is required unless --write-template is used")

    errors = validate_rows(read_rows(args.input), Decimal(args.tolerance))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(f"Validation failed with {len(errors)} error(s)")
    print("PASS: company detail data structure, units, sources, and H1 reconciliation")


if __name__ == "__main__":
    main()
