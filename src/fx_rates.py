#!/usr/bin/env python3
"""Fetch traceable period-average FX rates from the ECB reference-rate API."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from io import StringIO
from pathlib import Path
from typing import Callable

import requests
import urllib3


ECB_DATA_URL = "https://data-api.ecb.europa.eu/service/data/EXR"
ECB_DOCUMENTATION_URL = "https://data.ecb.europa.eu/help/api/data"
SUPPORTED_ECB_CURRENCIES = {"EUR", "JPY", "CNY"}
CBC_TWD_DAILY_URL = "https://cpx.cbc.gov.tw/api/OpenData/FTDOpenData_Day"


class FxRateError(ValueError):
    """Raised when a requested FX conversion cannot be resolved safely."""


@dataclass(frozen=True)
class FxResolution:
    currency: str
    usd_per_unit: Decimal
    method: str
    source_url: str
    start_date: str
    end_date: str
    observation_count: int
    evidence_csv: str = ""
    evidence_json: str = ""

    def as_json(self) -> dict[str, str | int]:
        payload = asdict(self)
        payload["usd_per_unit"] = str(self.usd_per_unit)
        return payload


def _date(value: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise FxRateError(f"汇率期间必须为 YYYY-MM-DD：{value}") from exc


def build_ecb_url(currency: str, start_date: str, end_date: str) -> str:
    currency = currency.upper()
    _date(start_date)
    _date(end_date)
    if currency == "USD":
        return ECB_DOCUMENTATION_URL
    if currency not in SUPPORTED_ECB_CURRENCIES:
        raise FxRateError(f"ECB自动汇率暂不覆盖币种：{currency}")
    key = "D.USD.EUR.SP00.A" if currency == "EUR" else f"D.USD+{currency}.EUR.SP00.A"
    return f"{ECB_DATA_URL}/{key}?startPeriod={start_date}&endPeriod={end_date}&format=csvdata"


def _write_evidence(
    evidence_dir: Path | None, currency: str, start_date: str, end_date: str,
    body: str, payload: dict, raw_suffix: str = "csv",
) -> tuple[str, str]:
    if evidence_dir is None:
        return "", ""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]
    stem = f"ecb_exr_{currency}_{start_date}_{end_date}_{digest}"
    csv_path = evidence_dir / f"{stem}.{raw_suffix}"
    json_path = evidence_dir / f"{stem}.json"
    csv_path.write_text(body, encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(csv_path), str(json_path)


def period_average_usd_per_unit(
    currency: str,
    start_date: str,
    end_date: str,
    evidence_dir: Path | None = None,
    http_get: Callable[..., object] = requests.get,
) -> FxResolution:
    """Return arithmetic daily average USD per 1 unit of currency for a flow period."""
    currency = str(currency or "").upper().strip()
    start = _date(start_date)
    end = _date(end_date)
    if start > end:
        raise FxRateError("汇率起始日不得晚于结束日")
    if currency == "USD":
        return FxResolution(
            currency="USD", usd_per_unit=Decimal("1"), method="usd_fixed_parity",
            source_url=ECB_DOCUMENTATION_URL, start_date=str(start), end_date=str(end), observation_count=0,
        )
    if currency == "TWD":
        try:
            response = http_get(CBC_TWD_DAILY_URL, timeout=30, headers={"Accept": "application/json"})
            response.raise_for_status()
        except requests.exceptions.SSLError:
            # The CBC open-data host currently serves a legacy certificate chain
            # rejected by newer Python/OpenSSL builds. Restrict this compatibility
            # retry to the fixed official endpoint and retain the raw response hash.
            if http_get is not requests.get:
                raise FxRateError(f"台湾央行汇率请求失败：TWD {start}至{end}")
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            response = requests.get(CBC_TWD_DAILY_URL, timeout=30, headers={"Accept": "application/json"}, verify=False)
            response.raise_for_status()
        except Exception as exc:
            raise FxRateError(f"台湾央行汇率请求失败：TWD {start}至{end}") from exc
        body = str(response.text)
        try:
            rows = response.json()
        except Exception as exc:
            raise FxRateError("台湾央行TWD汇率响应不是有效JSON") from exc
        rates = []
        for row in rows:
            raw_date = str(row.get("日期") or "")
            raw_rate = str(row.get("NTD_USD") or "").strip()
            if len(raw_date) != 8 or not raw_rate:
                continue
            observed = date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8]))
            if start <= observed <= end:
                rates.append(Decimal("1") / Decimal(raw_rate))
        if not rates:
            raise FxRateError(f"台湾央行在 {start} 至 {end} 未返回可用的 TWD/USD 日数据")
        average = (sum(rates) / Decimal(len(rates))).quantize(Decimal("0.0000000001"), rounding=ROUND_HALF_UP)
        evidence_payload = {
            "provider": "Central Bank of the Republic of China (Taiwan)", "currency": "TWD",
            "method": "daily_arithmetic_average_usd_per_unit", "source_url": CBC_TWD_DAILY_URL,
            "start_date": str(start), "end_date": str(end), "observation_count": len(rates),
            "usd_per_unit": str(average),
        }
        evidence_csv, evidence_json = _write_evidence(evidence_dir, "TWD", str(start), str(end), body, evidence_payload, "source.json")
        return FxResolution(
            currency="TWD", usd_per_unit=average, method="cbc_taiwan_daily_arithmetic_average_usd_per_unit",
            source_url=CBC_TWD_DAILY_URL, start_date=str(start), end_date=str(end), observation_count=len(rates),
            evidence_csv=evidence_csv, evidence_json=evidence_json,
        )
    url = build_ecb_url(currency, str(start), str(end))
    try:
        response = http_get(url, timeout=30, headers={"Accept": "text/csv"})
        response.raise_for_status()
    except Exception as exc:
        raise FxRateError(f"ECB汇率请求失败：{currency} {start}至{end}") from exc
    body = str(response.text)
    rows = list(csv.DictReader(StringIO(body)))
    by_date: dict[str, dict[str, Decimal]] = {}
    for row in rows:
        observed_currency = str(row.get("CURRENCY") or "").upper()
        observed_date = str(row.get("TIME_PERIOD") or "")
        value = str(row.get("OBS_VALUE") or "").strip()
        if observed_currency in {"USD", currency} and observed_date and value:
            by_date.setdefault(observed_date, {})[observed_currency] = Decimal(value)
    rates: list[Decimal] = []
    for values in by_date.values():
        usd_per_eur = values.get("USD")
        if usd_per_eur is None:
            continue
        if currency == "EUR":
            rates.append(usd_per_eur)
        elif values.get(currency):
            rates.append(usd_per_eur / values[currency])
    if not rates:
        raise FxRateError(f"ECB在 {start} 至 {end} 未返回可用的 {currency}/USD 同日观测值")
    average = (sum(rates) / Decimal(len(rates))).quantize(Decimal("0.0000000001"), rounding=ROUND_HALF_UP)
    evidence_payload = {
        "provider": "ECB EXR", "currency": currency, "method": "daily_arithmetic_average_usd_per_unit",
        "source_url": url, "start_date": str(start), "end_date": str(end),
        "observation_count": len(rates), "usd_per_unit": str(average),
    }
    evidence_csv, evidence_json = _write_evidence(evidence_dir, currency, str(start), str(end), body, evidence_payload)
    return FxResolution(
        currency=currency, usd_per_unit=average, method="daily_arithmetic_average_usd_per_unit",
        source_url=url, start_date=str(start), end_date=str(end), observation_count=len(rates),
        evidence_csv=evidence_csv, evidence_json=evidence_json,
    )
