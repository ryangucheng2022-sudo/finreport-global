"""Schema-drift contract tests (sanitized fixtures, synthetic values).

Pins the two upstream response shapes the collectors depend on, exercised
through the real parsers:
- Eastmoney US F10 income payload: envelope result.data[], items keyed by
  REPORT ("2026/Q6") and ITEM_NAME (营业收入/毛利) with AMOUNT values.
- MSN financials rows: incomeStatement.revenue.totalRevenue plus currency
  and report/end dates.
If a source renames a field, these tests fail instead of the pipeline
silently producing empty tables. Refresh fixtures by re-capturing a
response and replacing values with synthetic ones, keeping field names.
"""
import json, os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
FIX = os.path.join(HERE, 'fixtures')

import fetch_eastmoney_us_margins as em
import overseas_auto_financials as oaf


class TestEastmoneyContract(unittest.TestCase):
    def setUp(self):
        self.payload = json.load(open(os.path.join(FIX, 'eastmoney_us_income.json'), encoding='utf-8'))

    def test_envelope_navigation(self):
        rows = (self.payload.get('result') or {}).get('data') or []
        self.assertEqual(len(rows), 4)
        for row in rows:
            for key in ('REPORT', 'ITEM_NAME', 'AMOUNT'):
                self.assertIn(key, row)

    def test_parser_computes_margin(self):
        rows = (self.payload.get('result') or {}).get('data') or []
        self.assertAlmostEqual(em.h1_margin(rows, '2026'), 0.4)


class TestMsnContract(unittest.TestCase):
    def test_extract_msn_reads_fixture(self):
        records = json.load(open(os.path.join(FIX, 'msn_financials.json'), encoding='utf-8'))
        out = oaf.extract_msn('Fixture Co', 2026, records, 'h1')
        self.assertIsNotNone(out)
        self.assertEqual(out['revenue'], 2000000)
        self.assertAlmostEqual(out['gross_margin'], 0.4)


if __name__ == '__main__':
    unittest.main()
