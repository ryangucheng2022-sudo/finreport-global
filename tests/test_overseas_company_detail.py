#!/usr/bin/env python3
"""Tests for integrated overseas company-detail validation."""

from decimal import Decimal
import sys
from pathlib import Path
from function_test_loader import load_function_tests

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SCRIPT_DIR))

from overseas_validate_company_detail import validate_rows  # noqa: E402


SOURCE = "https://example.com/official"


def row(section: str, role: str, value: str, metric_type: str = "amount", unit: str = "currency_K") -> dict[str, str]:
    return {
        "company": "TI",
        "section": section,
        "period_role": role,
        "dimension": "consolidated",
        "metric": "revenue",
        "metric_type": metric_type,
        "period_current": f"2026 {role}",
        "value_current": value,
        "period_compare": f"2025 {role}",
        "value_compare": value,
        "currency": "USD" if metric_type != "rate" else "",
        "unit": unit,
        "source_current": SOURCE,
        "source_compare": SOURCE,
        "notes": "",
    }


def test_valid_h1_reconciliation() -> None:
    rows = [row("h1_summary", "H1", "300"), row("quarter", "Q1", "100"), row("quarter", "Q2", "200")]
    assert validate_rows(rows) == []


def test_reconciliation_error() -> None:
    rows = [row("h1_summary", "H1", "301"), row("quarter", "Q1", "100"), row("quarter", "Q2", "200")]
    assert validate_rows(rows, Decimal("0"))[0].startswith("reconciliation:")


def test_rate_requires_percent() -> None:
    bad = row("h1_summary", "H1", "50", metric_type="rate", unit="currency_K")
    assert any("rate must use percent" in error for error in validate_rows([bad]))


if __name__ == "__main__":
    test_valid_h1_reconciliation()
    test_reconciliation_error()
    test_rate_requires_percent()
    print("ok")
def load_tests(loader, tests, pattern):
    return load_function_tests(sys.modules[__name__])
