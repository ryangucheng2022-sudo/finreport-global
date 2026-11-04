#!/usr/bin/env python3
"""Tests for the non-destructive overseas official-source monitor."""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SCRIPT_DIR))

from overseas_monitor import build_source_map, summarize_candidates, write_timeout_candidates  # noqa: E402


class TestOverseasMonitor(unittest.TestCase):
    def test_source_map_uses_reviewed_official_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            normalized = root / "normalized.csv"
            with normalized.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["company", "target_source", "compare_source"],
                )
                writer.writeheader()
                writer.writerow({
                    "company": "安森美 onsemi",
                    "target_source": "https://investor.onsemi.com/target-a; https://investor.onsemi.com/target-b",
                    "compare_source": "https://investor.onsemi.com/compare",
                })
            source_map = root / "source_map.csv"
            self.assertEqual(build_source_map(normalized, source_map), 2)
            with source_map.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["company_key"], "onsemi")
            self.assertEqual(rows[0]["period_role"], "target")
            self.assertIn("target-b", rows[0]["source_urls"])

    def test_summary_preserves_review_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = root / "candidates.csv"
            fields = [
                "company_key", "company", "period_role", "candidate_revenue",
                "candidate_unit", "candidate_currency", "confidence", "needs_review",
                "source_url", "notes",
            ]
            with candidates.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow({
                    "company_key": "TI", "company": "德州仪器 TI", "period_role": "target",
                    "candidate_revenue": "5000", "candidate_unit": "millions",
                    "candidate_currency": "USD", "confidence": "90", "needs_review": "no",
                    "source_url": "https://investor.ti.com/official", "notes": "candidate",
                })
                writer.writerow({
                    "company_key": "TI", "company": "德州仪器 TI", "period_role": "compare",
                    "candidate_revenue": "4000", "candidate_unit": "millions",
                    "candidate_currency": "USD", "confidence": "70", "needs_review": "yes",
                    "source_url": "https://investor.ti.com/official-old", "notes": "review",
                })
            status = root / "status.json"
            payload = summarize_candidates(candidates, status)
            self.assertEqual(payload["high_confidence_groups"], 1)
            self.assertEqual(payload["needs_review_groups"], 1)
            self.assertTrue(payload["requires_review"])
            self.assertIn("不得覆盖", payload["policy"])
            self.assertEqual(json.loads(status.read_text(encoding="utf-8"))["groups"], 2)

    def test_timeout_rows_keep_formal_data_out_of_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_map = root / "source_map.csv"
            with source_map.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["company_key", "period_role", "source_urls"])
                writer.writeheader()
                writer.writerow({
                    "company_key": "TI", "period_role": "target",
                    "source_urls": "https://investor.ti.com/official",
                })
            candidates = root / "candidates.csv"
            self.assertEqual(write_timeout_candidates(source_map, candidates, 120), 1)
            with candidates.open("r", encoding="utf-8-sig", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["candidate_revenue"], "")
            self.assertEqual(row["needs_review"], "yes")
            self.assertIn("120", row["notes"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
