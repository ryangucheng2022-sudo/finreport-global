#!/usr/bin/env python3
"""Generate an official-source search plan for overseas semiconductor revenue."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = SKILL_DIR / "config" / "watchlist.json"


QUARTER_LABELS = {
    1: "first quarter",
    2: "second quarter",
    3: "third quarter",
    4: "fourth quarter",
}

HALF_LABELS = {
    1: "first half",
    2: "second half",
}


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def fiscal_period(company_key: str, year: int, period_type: str, period: str) -> tuple[str, int]:
    """Return approximate fiscal label/year for search templates.

    This is a planning helper; the final report must still use actual company
    disclosure labels found in official releases.
    """

    if period_type == "annual":
        return "full year", year

    period_num = int(period)
    if period_type == "half_year":
        period_label = HALF_LABELS.get(period_num, f"half {period_num}")
    else:
        period_label = QUARTER_LABELS.get(period_num, f"quarter {period_num}")

    if company_key == "Infineon":
        if period_type == "quarter":
            fiscal_q = {1: 2, 2: 3, 3: 4, 4: 1}[period_num]
            fiscal_year = year if period_num in (1, 2, 3) else year + 1
            return f"Q{fiscal_q}", fiscal_year
        if period_type == "half_year":
            return ("first half" if period_num == 1 else "second half"), year

    if company_key == "Microchip":
        if period_type == "quarter":
            fiscal_q = {1: 4, 2: 1, 3: 2, 4: 3}[period_num]
            fiscal_year = year if period_num == 1 else year + 1
            return f"Q{fiscal_q}", fiscal_year
        if period_type == "half_year":
            return ("second half" if period_num == 1 else "first half"), year

    if company_key == "ADI":
        if period_type == "quarter":
            fiscal_q = {1: 2, 2: 3, 3: 4, 4: 1}[period_num]
            fiscal_year = year if period_num in (1, 2, 3) else year + 1
            return f"Q{fiscal_q}", fiscal_year
        if period_type == "half_year":
            return ("first half" if period_num == 1 else "second half"), year

    return period_label, year


def calendar_period_label(period_type: str, period: str, year: int) -> str:
    if period_type == "annual":
        return f"{year} full year"
    period_num = int(period)
    if period_type == "half_year":
        return f"{year} H{period_num}"
    return f"{year} Q{period_num}"


def query_period_words(period_type: str, period: str) -> str:
    if period_type == "annual":
        return "full year"
    period_num = int(period)
    if period_type == "half_year":
        return HALF_LABELS.get(period_num, f"half {period_num}")
    return QUARTER_LABELS.get(period_num, f"quarter {period_num}")


def generate_rows(args: argparse.Namespace) -> list[dict]:
    config = load_config()
    company_keys = args.companies or config["default_companies"]
    rows = []
    for key in company_keys:
        company = config["companies"][key]
        fiscal_label, fiscal_year = fiscal_period(key, args.year, args.period_type, args.period)
        period_label = calendar_period_label(args.period_type, args.period, args.year)
        period_words = query_period_words(args.period_type, args.period)
        template = company["query_templates"][args.period_type]
        query = template.format(
            year=args.year,
            period_label=period_words,
            fiscal_period_label=fiscal_label,
            fiscal_year=fiscal_year,
        )
        rows.append(
            {
                "company_key": key,
                "company": company["display_name"],
                "legal_name": company["legal_name"],
                "target_period": period_label,
                "expected_reporting_currency": company["reporting_currency"],
                "fiscal_planning_label": f"FY{fiscal_year} {fiscal_label}",
                "source_domains": "; ".join(company["primary_domains"]),
                "official_source_url": company.get("official_monthly_source_url", ""),
                "official_source_unit": company.get("official_monthly_unit", ""),
                "search_query": query,
                "fiscal_note": company["fiscal_note"],
            }
        )
    return rows


def write_csv(rows: list[dict], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--period-type", choices=["quarter", "half_year", "annual"], required=True)
    parser.add_argument("--period", default="1", help="Quarter 1-4 or half-year 1-2; ignored for annual.")
    parser.add_argument("--companies", nargs="*", help="Company keys from config, e.g. TI Infineon NXP")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.period_type == "quarter" and int(args.period) not in (1, 2, 3, 4):
        raise SystemExit("--period must be 1-4 for quarter")
    if args.period_type == "half_year" and int(args.period) not in (1, 2):
        raise SystemExit("--period must be 1-2 for half_year")

    rows = generate_rows(args)
    write_csv(rows, args.output)
    print(f"Wrote {len(rows)} source-plan rows to {args.output}")


if __name__ == "__main__":
    main()
