#!/usr/bin/env python3
"""Append H1 gross-margin fields from Eastmoney US F10 income statements."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import requests

API = "https://datacenter-web.eastmoney.com/api/data/v1/get"
SYMBOLS = {
    "德州仪器 TI": "TXN.O", "恩智浦 NXP": "NXPI.O", "意法半导体 STM": "STM.N",
    "安森美 onsemi": "ON.O", "芯源 MPS": "MPWR.O",
}
MANUAL_FALLBACKS = {
    # Official H1/current and comparable-period gross-margin disclosures.
    "英飞凌 Infineon": (0.398297846, 0.410143934, "official_filing"),
    "瑞萨 Renesas": (0.586, 0.558, "official_filing"),
}


def records(symbol: str) -> list[dict]:
    params = {"reportName": "RPT_USF10_FN_INCOME", "columns": "ALL", "filter": f'(SECUCODE="{symbol}")', "pageNumber": 1, "pageSize": 500, "sortTypes": "-1", "sortColumns": "REPORT_DATE", "source": "WEB", "client": "WEB"}
    payload = requests.get(API, params=params, timeout=30).json()
    return (payload.get("result") or {}).get("data") or []


def h1_margin(data: list[dict], year: str) -> float | None:
    amounts = {}
    for item in data:
        if item.get("REPORT") == f"{year}/Q6" and item.get("ITEM_NAME") in ("营业收入", "毛利"):
            amounts[item["ITEM_NAME"]] = float(item["AMOUNT"])
    return amounts["毛利"] / amounts["营业收入"] if amounts.get("营业收入") else None


def sum_margin(data: list[dict], periods: list[str]) -> float | None:
    revenue = gross = 0.0
    for item in data:
        if item.get("REPORT") in periods and item.get("ITEM_NAME") in ("营业收入", "毛利"):
            if item["ITEM_NAME"] == "营业收入": revenue += float(item["AMOUNT"])
            else: gross += float(item["AMOUNT"])
    return gross / revenue if revenue else None


def margin_for(company: str) -> tuple[float | None, float | None, str]:
    if company in MANUAL_FALLBACKS:
        return MANUAL_FALLBACKS[company]
    if company == "亚德诺 ADI":
        data = records("ADI.O")
        return sum_margin(data, ["2026/Q2", "2026/Q3"]), sum_margin(data, ["2025/Q2", "2025/Q3"]), "eastmoney_us"
    if company == "微芯 Microchip":
        data = records("MCHP.O")
        return sum_margin(data, ["2025/Q4", "2026/Q1"]), sum_margin(data, ["2024/Q4", "2025/Q1"]), "eastmoney_us"
    symbol = SYMBOLS.get(company)
    if not symbol:
        return None, None, "msn_crosscheck_required"
    data = records(symbol)
    return h1_margin(data, "2026"), h1_margin(data, "2025"), "eastmoney_us"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with args.input.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0]) if rows else []
    for field in ("target_gross_margin", "compare_gross_margin", "gross_margin_source"):
        if field not in fields: fields.append(field)
    for row in rows:
        current, prior, source = margin_for(row.get("company", ""))
        row["target_gross_margin"] = f"{current:.6%}" if current is not None else ""
        row["compare_gross_margin"] = f"{prior:.6%}" if prior is not None else ""
        row["gross_margin_source"] = source
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


if __name__ == "__main__":
    main()
