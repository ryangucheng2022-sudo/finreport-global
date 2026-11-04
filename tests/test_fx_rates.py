from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fx_rates import FxRateError, period_average_usd_per_unit  # noqa: E402


CSV_BODY = """KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE\nEXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-01-02,1.2000\nEXR.D.JPY.EUR.SP00.A,D,JPY,EUR,SP00,A,2026-01-02,180.0000\nEXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-01-05,1.1000\nEXR.D.JPY.EUR.SP00.A,D,JPY,EUR,SP00,A,2026-01-05,165.0000\n"""


class Response:
    text = CSV_BODY

    def raise_for_status(self):
        return None


def fake_get(*_args, **_kwargs):
    return Response()


class TwdResponse:
    text = '[{"日期":"20260102","NTD_USD":"32"},{"日期":"20260105","NTD_USD":"40"}]'

    def raise_for_status(self):
        return None

    def json(self):
        return [{"日期": "20260102", "NTD_USD": "32"}, {"日期": "20260105", "NTD_USD": "40"}]


def fake_twd_get(*_args, **_kwargs):
    return TwdResponse()


class FxRateTests(unittest.TestCase):
    def test_jpy_cross_rate_is_derived_from_same_day_ecb_observations(self):
        result = period_average_usd_per_unit("JPY", "2026-01-01", "2026-01-06", http_get=fake_get)
        self.assertEqual(result.usd_per_unit, Decimal("0.0066666667"))
        self.assertEqual(result.observation_count, 2)
        self.assertIn("USD+JPY", result.source_url)

    def test_eur_rate_and_raw_evidence_are_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            result = period_average_usd_per_unit("EUR", "2026-01-01", "2026-01-06", Path(directory), fake_get)
            self.assertEqual(result.usd_per_unit, Decimal("1.1500000000"))
            self.assertTrue(Path(result.evidence_csv).is_file())
            self.assertTrue(Path(result.evidence_json).is_file())

    def test_unknown_currency_does_not_silently_guess(self):
        with self.assertRaises(FxRateError):
            period_average_usd_per_unit("GBP", "2026-01-01", "2026-01-06", http_get=fake_get)

    def test_twd_uses_taiwan_central_bank_daily_rates(self):
        result = period_average_usd_per_unit("TWD", "2026-01-01", "2026-01-06", http_get=fake_twd_get)
        self.assertEqual(result.usd_per_unit, Decimal("0.0281250000"))
        self.assertEqual(result.observation_count, 2)
        self.assertIn("cpx.cbc.gov.tw", result.source_url)


if __name__ == "__main__":
    unittest.main(verbosity=2)
