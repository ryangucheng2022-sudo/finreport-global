#!/usr/bin/env python3
"""Smoke test for the merged overseas revenue normalization module."""

from decimal import Decimal
import sys
from pathlib import Path
from function_test_loader import load_function_tests

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SCRIPT_DIR))

from overseas_normalize_revenue_report import growth_label, local_thousand, normalize_row, usd_thousand  # noqa: E402


def test_usd_thousand() -> None:
    assert usd_thousand("4.83", "billions", "1") == 4_830_000
    assert usd_thousand("3812", "millions", "1.1708") == 4_463_090


def test_growth_label() -> None:
    assert growth_label(Decimal("0.30")) == ("优秀", "#38761D")
    assert growth_label(Decimal("0.20")) == ("良好", "#6AA84F")
    assert growth_label(Decimal("0.10")) == ("一般", "#93C47D")
    assert growth_label(Decimal("0.00")) == ("持平", "#FFFFFF")
    assert growth_label(Decimal("-0.20")) == ("较差", "#EA9999")


def test_local_thousand() -> None:
    assert local_thousand("4.83", "billions") == 4_830_000
    assert local_thousand("3812", "millions") == 3_812_000


def test_usd_rows_need_no_manual_fx_or_period_dates() -> None:
    row = {
        "company": "TI", "type": "海外", "period_type": "quarter",
        "target_period_label": "2026 Q1", "compare_period_label": "2025 Q1",
        "target_revenue": "4.83", "target_unit": "billions", "target_currency": "USD",
        "target_fx_usd_per_unit": "", "target_source": "https://example.com/ti",
        "compare_revenue": "4.07", "compare_unit": "billions", "compare_currency": "USD",
        "compare_fx_usd_per_unit": "", "compare_source": "https://example.com/ti",
    }
    result = normalize_row(row)
    assert result["target_revenue_usd_thousand"] == 4_830_000
    assert result["target_fx_method"] == "usd_fixed_parity"


if __name__ == "__main__":
    test_usd_thousand()
    test_growth_label()
    test_local_thousand()
    print("ok")
def load_tests(loader, tests, pattern):
    return load_function_tests(sys.modules[__name__])
