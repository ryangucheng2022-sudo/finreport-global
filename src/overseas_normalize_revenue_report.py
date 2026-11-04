#!/usr/bin/env python3
"""Normalize captured revenue data to USD thousands and compute growth labels."""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from fx_rates import ECB_DOCUMENTATION_URL, FxRateError, period_average_usd_per_unit


FIELDS = [
    "company",
    "type",
    "period_type",
    "target_period_label",
    "compare_period_label",
    "target_period_start",
    "target_period_end",
    "target_revenue",
    "target_unit",
    "target_currency",
    "target_fx_usd_per_unit",
    "target_fx_source",
    "target_source",
    "compare_revenue",
    "compare_unit",
    "compare_currency",
    "compare_fx_usd_per_unit",
    "compare_fx_source",
    "compare_period_start",
    "compare_period_end",
    "compare_source",
    "notes",
]

OUTPUT_FIELDS = [
    "rank",
    "company",
    "type",
    "period_type",
    "target_period_label",
    "compare_period_label",
    "target_currency",
    "target_period_start",
    "target_period_end",
    "target_revenue_local_thousand",
    "target_fx_usd_per_unit",
    "target_fx_source",
    "target_fx_method",
    "compare_currency",
    "compare_period_start",
    "compare_period_end",
    "compare_revenue_local_thousand",
    "compare_fx_usd_per_unit",
    "compare_fx_source",
    "compare_fx_method",
    "target_revenue_usd_thousand",
    "compare_revenue_usd_thousand",
    "change_usd_thousand",
    "growth_rate",
    "growth_label",
    "growth_fill",
    "target_source",
    "compare_source",
    "notes",
]

UNIT_MULTIPLIERS = {
    "ones": Decimal("1"),
    "thousands": Decimal("1000"),
    "millions": Decimal("1000000"),
    "billions": Decimal("1000000000"),
}


def d(value: str | int | float | Decimal) -> Decimal:
    text = str(value).strip().replace(",", "")
    if text == "":
        return Decimal("0")
    return Decimal(text)


def usd_thousand(revenue: str, unit: str, fx_usd_per_unit: str) -> int:
    if unit not in UNIT_MULTIPLIERS:
        raise ValueError(f"Unsupported unit: {unit}")
    value = d(revenue) * UNIT_MULTIPLIERS[unit] * d(fx_usd_per_unit) / Decimal("1000")
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def local_thousand(revenue: str, unit: str) -> int:
    """Convert a reported amount to thousands without changing currency."""
    if unit not in UNIT_MULTIPLIERS:
        raise ValueError(f"Unsupported unit: {unit}")
    value = d(revenue) * UNIT_MULTIPLIERS[unit] / Decimal("1000")
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def growth_label(rate: Decimal) -> tuple[str, str]:
    if rate >= Decimal("0.30"):
        return "优秀", "#38761D"
    if rate >= Decimal("0.20"):
        return "良好", "#6AA84F"
    if rate >= Decimal("0.10"):
        return "一般", "#93C47D"
    if rate >= Decimal("-0.10"):
        return "持平", "#FFFFFF"
    if rate <= Decimal("-0.20"):
        return "较差", "#EA9999"
    return "下滑", "#F4CCCC"


def resolve_fx(row: dict, role: str, auto_fx: bool, evidence_dir: Path | None) -> tuple[Decimal, str, str]:
    currency = str(row.get(f"{role}_currency") or "").upper().strip()
    provided = str(row.get(f"{role}_fx_usd_per_unit") or "").strip()
    source = str(row.get(f"{role}_fx_source") or "").strip()
    if provided:
        value = d(provided)
        if value <= 0:
            raise ValueError(f"{role}_fx_usd_per_unit 必须大于0")
        return value, source, "manual_override"
    if not auto_fx:
        raise ValueError(f"{role}期缺少汇率；请填写 {role}_fx_usd_per_unit 或启用自动汇率")
    if currency == "USD":
        return Decimal("1"), ECB_DOCUMENTATION_URL, "usd_fixed_parity"
    start = str(row.get(f"{role}_period_start") or "").strip()
    end = str(row.get(f"{role}_period_end") or "").strip()
    if not start or not end:
        raise ValueError(f"{role}期自动汇率需要 {role}_period_start 和 {role}_period_end")
    try:
        resolved = period_average_usd_per_unit(currency, start, end, evidence_dir)
    except FxRateError as exc:
        raise ValueError(f"{role}期自动汇率失败：{exc}") from exc
    return resolved.usd_per_unit, resolved.source_url, resolved.method


def normalize_row(row: dict, auto_fx: bool = True, evidence_dir: Path | None = None) -> dict:
    target_local = local_thousand(row["target_revenue"], row["target_unit"])
    compare_local = local_thousand(row["compare_revenue"], row["compare_unit"])
    target_fx, target_fx_source, target_fx_method = resolve_fx(row, "target", auto_fx, evidence_dir)
    compare_fx, compare_fx_source, compare_fx_method = resolve_fx(row, "compare", auto_fx, evidence_dir)
    target = usd_thousand(row["target_revenue"], row["target_unit"], target_fx)
    compare = usd_thousand(row["compare_revenue"], row["compare_unit"], compare_fx)
    if compare == 0:
        rate = Decimal("0")
    else:
        rate = Decimal(target - compare) / Decimal(compare)
    label, fill = growth_label(rate)
    return {
        "rank": "",
        "company": row["company"],
        "type": row.get("type", "海外"),
        "period_type": row["period_type"],
        "target_period_label": row["target_period_label"],
        "compare_period_label": row["compare_period_label"],
        "target_currency": row["target_currency"],
        "target_period_start": row.get("target_period_start", ""),
        "target_period_end": row.get("target_period_end", ""),
        "target_revenue_local_thousand": target_local,
        "target_fx_usd_per_unit": target_fx,
        "target_fx_source": target_fx_source,
        "target_fx_method": target_fx_method,
        "compare_currency": row["compare_currency"],
        "compare_period_start": row.get("compare_period_start", ""),
        "compare_period_end": row.get("compare_period_end", ""),
        "compare_revenue_local_thousand": compare_local,
        "compare_fx_usd_per_unit": compare_fx,
        "compare_fx_source": compare_fx_source,
        "compare_fx_method": compare_fx_method,
        "target_revenue_usd_thousand": target,
        "compare_revenue_usd_thousand": compare,
        "change_usd_thousand": target - compare,
        "growth_rate": f"{(rate * Decimal('100')).quantize(Decimal('0.1'))}%",
        "growth_label": label,
        "growth_fill": fill,
        "target_source": row["target_source"],
        "compare_source": row["compare_source"],
        "notes": row.get("notes", ""),
    }


def read_input(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "| 排名 | 公司 | 口径 | 本期收入(千美元) | 上年同期(千美元) | 同比 | 等级 |",
        "|---:|---|---|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {rank} | {company} | {target_period_label} / {compare_period_label} | {target_revenue_usd_thousand:,} | {compare_revenue_usd_thousand:,} | {growth_rate} | {growth_label} |".format(
                **row
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_template(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow(
            {
                "company": "德州仪器 TI",
                "type": "海外",
                "period_type": "quarter",
                "target_period_label": "2026 Q1",
                "compare_period_label": "2025 Q1",
                "target_period_start": "2026-01-01",
                "target_period_end": "2026-03-31",
                "target_revenue": "4.83",
                "target_unit": "billions",
                "target_currency": "USD",
                "target_fx_usd_per_unit": "",
                "target_fx_source": "",
                "target_source": "https://investor.ti.com/...",
                "compare_revenue": "4.07",
                "compare_unit": "billions",
                "compare_currency": "USD",
                "compare_fx_usd_per_unit": "",
                "compare_fx_source": "",
                "compare_period_start": "2025-01-01",
                "compare_period_end": "2025-03-31",
                "compare_source": "https://investor.ti.com/...",
                "notes": "Example row; replace with verified official data.",
            }
        )
    print(f"Wrote template to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--fx-evidence-dir", type=Path, help="Directory for ECB raw responses and FX audit records")
    parser.add_argument("--no-auto-fx", action="store_true", help="Require explicit FX values in every input row")
    parser.add_argument("--write-template", type=Path)
    args = parser.parse_args()

    if args.write_template:
        write_template(args.write_template)
        return

    if not args.input or not args.output:
        raise SystemExit("--input and --output are required unless --write-template is used")

    evidence_dir = args.fx_evidence_dir or (args.output.parent / "raw" / "fx")
    rows = [normalize_row(row, auto_fx=not args.no_auto_fx, evidence_dir=evidence_dir) for row in read_input(args.input)]
    rows.sort(key=lambda item: int(item["target_revenue_usd_thousand"]), reverse=True)
    for idx, row in enumerate(rows, 1):
        row["rank"] = idx

    write_csv(rows, args.output)
    if args.markdown:
        write_markdown(rows, args.markdown)
    print(f"Wrote {len(rows)} normalized rows to {args.output}")


if __name__ == "__main__":
    main()
