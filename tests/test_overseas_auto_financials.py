#!/usr/bin/env python3

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SCRIPT_DIR))

from overseas_auto_financials import (  # noqa: E402
    build_row,
    extract_eastmoney,
    extract_msn,
    msn_period_types,
    period_mode_for,
    period_tokens,
    silergy_monthly_h1,
)


class TestOverseasAutoFinancials(unittest.TestCase):
    def test_ti_h1_uses_cumulative_f10_and_preserves_absolute_units(self):
        records = [
            {"REPORT": "2026/Q6", "ITEM_NAME": "营业收入", "AMOUNT": 10_288_000_000, "CURRENCY": "美元", "START_DATE": "2026-01-01", "REPORT_DATE": "2026-06-30"},
            {"REPORT": "2026/Q6", "ITEM_NAME": "毛利", "AMOUNT": 6_151_000_000, "CURRENCY": "美元", "START_DATE": "2026-01-01", "REPORT_DATE": "2026-06-30"},
        ]
        result = extract_eastmoney("TI", 2026, records)
        self.assertEqual(result["revenue"], 10_288_000_000)
        self.assertAlmostEqual(result["gross_margin"], 6_151 / 10_288)

    def test_adi_natural_h1_is_fiscal_q2_plus_q3(self):
        self.assertEqual(period_tokens("ADI", 2026), ["2026/Q2", "2026/Q3"])
        records = []
        for quarter, revenue, gross in (("q2", 2_000, 1_200), ("q3", 3_000, 1_500)):
            records.append({
                "year": 2026, "type": quarter,
                "incomeStatement": {
                    "currency": "USD", "reportDate": "2026-06-30T00:00:00Z", "endDate": "2026-06-30T00:00:00Z",
                    "revenue": {"totalRevenue": revenue}, "expense": {"grossProfit": gross},
                },
            })
        result = extract_msn("ADI", 2026, records)
        self.assertEqual(result["revenue"], 5_000)
        self.assertEqual(result["gross_profit"], 2_700)

    def test_calendar_h1_requires_both_msn_quarters(self):
        records = [{
            "year": 2026, "type": "q1",
            "incomeStatement": {"currency": "TWD", "reportDate": "2026-03-31", "endDate": "2026-03-31", "revenue": {"totalRevenue": 100}, "expense": {"grossProfit": 50}},
        }]
        self.assertIsNone(extract_msn("Silergy", 2026, records))

    def test_microchip_msn_uses_fiscal_q4_and_next_fiscal_q1(self):
        records = []
        for fiscal_year, quarter, revenue in ((2026, "q4", 1_300), (2027, "q1", 1_500)):
            records.append({
                "year": fiscal_year, "type": quarter,
                "incomeStatement": {
                    "currency": "USD", "reportDate": "2026-06-30", "endDate": "2026-06-30",
                    "revenue": {"totalRevenue": revenue}, "expense": {"grossProfit": revenue / 2},
                },
            })
        result = extract_msn("Microchip", 2026, records)
        self.assertEqual(result["revenue"], 2_800)

    def test_silergy_official_monthly_uses_june_usd_ytd(self):
        class Response:
            url = "https://www.silergy.com/news/financial?year=2026"
            text = '<table id="monReport"><tr><td rowspan="2">Jun</td><td>NTD</td><td>2,084,305</td><td>37.77%</td><td>10,868,527</td><td>25.54%</td></tr><tr><td>USD</td><td>65,911</td><td>29.19%</td><td>343,788</td><td>26.51%</td></tr></table>'
            def raise_for_status(self): return None
        class Session:
            def get(self, *_args, **_kwargs): return Response()
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            result, _ = silergy_monthly_h1(2026, "https://www.silergy.com/news/financial", Path(directory), Session())
        self.assertEqual(result["revenue"], 343_788_000)
        self.assertEqual(result["currency"], "USD")


class TestOverseasAnnual(unittest.TestCase):
    def test_period_mode_derivation(self):
        self.assertEqual(period_mode_for("2026-06-30"), "h1")
        self.assertEqual(period_mode_for("2025-12-31"), "annual")
        with self.assertRaises(ValueError):
            period_mode_for("2026-09-30")

    def test_annual_eastmoney_tokens_use_fiscal_year_quarters(self):
        self.assertEqual(
            period_tokens("TI", 2025, "annual"),
            ["2025/Q1", "2025/Q2", "2025/Q3", "2025/Q4"],
        )
        self.assertEqual(
            period_tokens("ADI", 2025, "annual"),
            ["2025/Q1", "2025/Q2", "2025/Q3", "2025/Q4"],
        )
        # Microchip Eastmoney labels sit one year below the MSN fiscal label.
        self.assertEqual(
            period_tokens("Microchip", 2026, "annual"),
            ["2025/Q1", "2025/Q2", "2025/Q3", "2025/Q4"],
        )

    def test_annual_msn_types_use_fiscal_year_quarters(self):
        self.assertEqual(
            msn_period_types("TI", 2025, "annual"),
            [(2025, "q1"), (2025, "q2"), (2025, "q3"), (2025, "q4")],
        )
        self.assertEqual(
            msn_period_types("Microchip", 2026, "annual"),
            [(2026, "q1"), (2026, "q2"), (2026, "q3"), (2026, "q4")],
        )

    def test_annual_eastmoney_sums_discrete_quarters(self):
        records = []
        for quarter, revenue in (("Q1", 100), ("Q2", 200), ("Q3", 300), ("Q4", 400)):
            records.append({"REPORT": f"2025/{quarter}", "ITEM_NAME": "营业收入", "AMOUNT": revenue, "CURRENCY": "美元", "START_DATE": "2025-01-01", "REPORT_DATE": "2025-12-31"})
            records.append({"REPORT": f"2025/{quarter}", "ITEM_NAME": "毛利", "AMOUNT": revenue / 2, "CURRENCY": "美元", "START_DATE": "2025-01-01", "REPORT_DATE": "2025-12-31"})
        result = extract_eastmoney("TI", 2025, records, "annual")
        self.assertEqual(result["revenue"], 1000)
        self.assertAlmostEqual(result["gross_margin"], 0.5)
        self.assertEqual(result["period_end"], "2025-12-31")

    def test_annual_msn_requires_all_four_fiscal_quarters(self):
        records = []
        for quarter, revenue in (("q1", 100), ("q2", 200), ("q3", 300)):
            records.append({
                "year": 2025, "type": quarter,
                "incomeStatement": {"currency": "USD", "reportDate": "2025-12-31", "endDate": "2025-12-31", "revenue": {"totalRevenue": revenue}, "expense": {"grossProfit": revenue / 2}},
            })
        self.assertIsNone(extract_msn("TI", 2025, records, "annual"))
        records.append({
            "year": 2025, "type": "q4",
            "incomeStatement": {"currency": "USD", "reportDate": "2025-12-31", "endDate": "2025-12-31", "revenue": {"totalRevenue": 400}, "expense": {"grossProfit": 200}},
        })
        result = extract_msn("TI", 2025, records, "annual")
        self.assertEqual(result["revenue"], 1000)
        self.assertEqual(result["period_end"], "2025-12-31")

    def test_annual_build_row_labels_and_period_type(self):
        candidate = {
            "currency": "USD", "revenue": 5_000_000, "gross_profit": 2_000_000, "gross_margin": 0.4,
            "period_start": "2025-01-01", "period_end": "2025-12-31", "periods": [], "evidence": [],
        }
        row = build_row(
            "TI", {"display_name": "德州仪器"}, 2025, 2024,
            candidate, candidate, "eastmoney_us", "eastmoney_us",
            {"target_eastmoney_us": "https://example.com", "compare_eastmoney_us": "https://example.com"},
            "matched", Path("/tmp"), {}, "annual",
        )
        self.assertEqual(row["period_type"], "annual")
        self.assertEqual(row["target_period_label"], "2025 年度")
        self.assertEqual(row["compare_period_label"], "2024 年度")

    def test_silergy_official_monthly_annual_uses_december_ytd(self):
        class Response:
            url = "https://www.silergy.com/news/financial?year=2026"
            text = '<table id="monReport"><tr><td rowspan="2">Dec</td><td>NTD</td><td>2,000,000</td><td>10.00%</td><td>20,000,000</td><td>11.00%</td></tr><tr><td>USD</td><td>60,000</td><td>9.00%</td><td>650,000</td><td>12.00%</td></tr></table>'
            def raise_for_status(self): return None
        class Session:
            def get(self, *_args, **_kwargs): return Response()
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            result, _ = silergy_monthly_h1(2026, "https://www.silergy.com/news/financial", Path(directory), Session(), "annual")
        self.assertEqual(result["revenue"], 650_000_000)
        self.assertEqual(result["period_end"], "2026-12-31")
        self.assertEqual(len(result["periods"]), 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
