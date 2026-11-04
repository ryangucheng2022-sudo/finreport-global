#!/usr/bin/env python3
"""Fetch overseas peer H1/annual financials from Eastmoney F10 and MSN Finance.

Eastmoney is the primary source where its US F10 universe has coverage. MSN is
always attempted as a cross-check and becomes the selected source when F10 is
unavailable. A reviewed/normalized CSV may be supplied as an optional fallback
or explicit override. Raw API responses and a field-level audit are retained.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import html
import re
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests

from fiscal_calendar import eastmoney_fiscal_year_tokens, fiscal_year_bounds, msn_fiscal_year_quarters
from fx_rates import FxRateError, period_average_usd_per_unit


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
COMPANY_CONFIG = SKILL_DIR / "config" / "watchlist.json"
EASTMONEY_API = "https://datacenter-web.eastmoney.com/api/data/v1/get"
MSN_AUTOSUGGEST_API = "https://services.bingapis.com/contentservices-finance.csautosuggest/api/v1/Query"
MSN_FINANCIALS_API = "https://api.msn.com/Finance/Equities/financialstatements"
# MSN_API_KEY is the public web client key that MSN Finance ships in its own
# page code for browser calls to its public finance API — it is not a private
# credential. Supply it via the MSN_API_KEY environment variable; when it is
# empty, MSN lookups are skipped and Eastmoney F10 remains the primary source.
MSN_API_KEY = os.environ.get("MSN_API_KEY", "")
SOURCE_URLS = {
    "eastmoney_us": "http://emweb.eastmoney.com/PC_USF10/pages/index.html?code={ticker}&type=web&color=w#/cwfx",
    "msn_crosscheck": "https://www.msn.com/zh-cn/money/watchlist?id={quote_id}&l3=L3_Financials",
}
EASTMONEY_CURRENCY = {"美元": "USD", "欧元": "EUR", "日元": "JPY", "新台币": "TWD", "人民币": "CNY"}
EASTMONEY_SYMBOLS = {
    "TI": "TXN.O", "NXP": "NXPI.O", "STM": "STM.N", "ADI": "ADI.O",
    "onsemi": "ON.O", "Microchip": "MCHP.O", "MPS": "MPWR.O",
}
OUTPUT_FIELDS = [
    "rank", "company", "type", "period_type", "target_period_label", "compare_period_label",
    "target_currency", "target_period_start", "target_period_end", "target_revenue_local_thousand",
    "target_fx_usd_per_unit", "target_fx_source", "target_fx_method", "compare_currency",
    "compare_period_start", "compare_period_end", "compare_revenue_local_thousand",
    "compare_fx_usd_per_unit", "compare_fx_source", "compare_fx_method",
    "target_revenue_usd_thousand", "compare_revenue_usd_thousand", "change_usd_thousand",
    "growth_rate", "growth_label", "growth_fill", "target_gross_profit_usd_thousand",
    "compare_gross_profit_usd_thousand", "target_gross_margin", "compare_gross_margin",
    "target_source", "compare_source", "target_source_level", "compare_source_level",
    "crosscheck_status", "status", "notes",
]


def load_companies() -> tuple[list[str], dict[str, dict[str, Any]]]:
    payload = json.loads(COMPANY_CONFIG.read_text(encoding="utf-8"))
    return payload["default_companies"], payload["companies"]


def safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def eastmoney_records(symbol: str, raw_dir: Path, session: requests.Session) -> tuple[list[dict], str]:
    params = {
        "reportName": "RPT_USF10_FN_INCOME", "columns": "ALL", "filter": f'(SECUCODE="{symbol}")',
        "pageNumber": 1, "pageSize": 500, "sortTypes": "-1", "sortColumns": "REPORT_DATE",
        "source": "WEB", "client": "WEB",
    }
    response = session.get(EASTMONEY_API, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    write_json(raw_dir / "eastmoney" / f"{safe_name(symbol)}.json", payload)
    return (payload.get("result") or {}).get("data") or [], response.url


def period_mode_for(target: str) -> str:
    """Derive the collection period mode from a report date."""
    if target.endswith("-06-30"):
        return "h1"
    if target.endswith("-12-31"):
        return "annual"
    raise ValueError(f"overseas-fetch 仅支持 06-30（半年度）或 12-31（年度）报告期：{target}")


def period_tokens(company: str, year: int, period_mode: str = "h1") -> list[str]:
    if period_mode == "annual":
        return eastmoney_fiscal_year_tokens(company, year)
    if company in {"ADI", "Infineon"}:
        return [f"{year}/Q2", f"{year}/Q3"]
    if company == "Microchip":
        return [f"{year - 1}/Q4", f"{year}/Q1"]
    return [f"{year}/Q6"]


def extract_eastmoney(company: str, year: int, records: list[dict], period_mode: str = "h1") -> dict[str, Any] | None:
    tokens = period_tokens(company, year, period_mode)
    selected = [row for row in records if row.get("REPORT") in tokens]
    amounts: dict[str, float] = {"营业收入": 0.0, "毛利": 0.0}
    found: set[str] = set()
    dates: list[str] = []
    currency = ""
    evidence: list[dict[str, Any]] = []
    for row in selected:
        item = row.get("ITEM_NAME")
        if item not in amounts or row.get("AMOUNT") is None:
            continue
        amounts[item] += float(row["AMOUNT"])
        found.add(item)
        dates.extend(str(row.get(key) or "")[:10] for key in ("START_DATE", "REPORT_DATE"))
        currency = EASTMONEY_CURRENCY.get(str(row.get("CURRENCY") or ""), str(row.get("CURRENCY") or ""))
        evidence.append({key: row.get(key) for key in ("SECUCODE", "REPORT", "REPORT_DATE", "START_DATE", "STD_ITEM_CODE", "ITEM_NAME", "AMOUNT", "CURRENCY")})
    if "营业收入" not in found:
        return None
    dates = sorted(value for value in dates if value)
    revenue = amounts["营业收入"]
    gross = amounts["毛利"] if "毛利" in found else None
    default_start, default_end = fiscal_year_bounds(company, year) if period_mode == "annual" else (f"{year}-01-01", f"{year}-06-30")
    return {
        "currency": currency or "USD", "revenue": revenue, "gross_profit": gross,
        "gross_margin": gross / revenue if gross is not None and revenue else None,
        "period_start": dates[0] if dates else default_start, "period_end": dates[-1] if dates else default_end,
        "periods": tokens, "evidence": evidence,
    }


def msn_quote_id(company: str, config: dict[str, Any], session: requests.Session) -> tuple[str | None, Any]:
    if config.get("msn_id"):
        return str(config["msn_id"]), {"configured": True, "quote_id": config["msn_id"]}
    query = config.get("msn_search_query") or config.get("legal_name") or company
    response = session.get(MSN_AUTOSUGGEST_API, params={"query": query, "market": "en-us", "count": 8}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    candidates = [json.loads(item) for item in (payload.get("data") or {}).get("stocks", [])]
    wanted = str(config.get("legal_name") or company).lower()
    tokens = [token for token in wanted.replace(",", " ").replace(".", " ").split() if len(token) > 2]
    def score(item: dict[str, Any]) -> int:
        text = " ".join(str(item.get(key) or "") for key in ("OS01W", "OS0LN", "RT0SN", "FriendlyName")).lower()
        return sum(token in text for token in tokens)
    choice = max(candidates, key=score, default=None)
    return (str(choice.get("SecId")) if choice and choice.get("SecId") else None), payload


def msn_financials(quote_id: str, raw_dir: Path, company: str, session: requests.Session) -> tuple[list[dict], str]:
    if not MSN_API_KEY:
        raise RuntimeError("MSN_API_KEY not set; skipping MSN source "
                           "(set the MSN_API_KEY env var to enable it)")
    params = {
        "$filter": f"_p eq '{quote_id}'", "$top": "200", "wrapodata": "false", "apikey": MSN_API_KEY,
        "ocid": "Peregrine", "cm": "zh-cn", "activityId": str(uuid.uuid4()),
    }
    response = session.get(MSN_FINANCIALS_API, params=params, timeout=30, headers={"Referer": "https://www.msn.com/"})
    response.raise_for_status()
    payload = response.json()
    write_json(raw_dir / "msn" / f"{safe_name(company)}.json", payload)
    return payload, response.url


def msn_period_types(company: str, year: int, period_mode: str = "h1") -> list[tuple[int, str]]:
    if period_mode == "annual":
        return msn_fiscal_year_quarters(company, year)
    if company in {"ADI", "Infineon"}:
        return [(year, "q2"), (year, "q3")]
    if company == "Microchip":
        # MSN labels Microchip by fiscal year: calendar Jan-Mar 2026 is FY2026
        # Q4 and calendar Apr-Jun 2026 is FY2027 Q1.
        return [(year, "q4"), (year + 1, "q1")]
    return [(year, "q1"), (year, "q2")]


def extract_msn(company: str, year: int, records: list[dict], period_mode: str = "h1") -> dict[str, Any] | None:
    wanted = set(msn_period_types(company, year, period_mode))
    selected = [row for row in records if (int(row.get("year") or 0), str(row.get("type") or "").lower()) in wanted]
    if len(selected) != len(wanted):
        return None
    revenue = 0.0
    gross = 0.0
    gross_complete = True
    dates: list[str] = []
    currency = ""
    evidence = []
    for row in selected:
        statement = row.get("incomeStatement") or {}
        revenue_data = statement.get("revenue") or {}
        expense = statement.get("expense") or {}
        amount = revenue_data.get("totalRevenue")
        if amount is None:
            return None
        revenue += float(amount)
        if expense.get("grossProfit") is None:
            gross_complete = False
        else:
            gross += float(expense["grossProfit"])
        currency = str(statement.get("currency") or currency)
        dates.extend(str(statement.get(key) or "")[:10] for key in ("reportDate", "endDate"))
        evidence.append({
            "year": row.get("year"), "type": row.get("type"), "reportDate": statement.get("reportDate"),
            "currency": statement.get("currency"), "totalRevenue": amount, "grossProfit": expense.get("grossProfit"),
            "grossMargin": revenue_data.get("grossMargin"), "source": statement.get("source"),
        })
    dates = sorted(value for value in dates if value)
    gross_value = gross if gross_complete else None
    default_start, default_end = fiscal_year_bounds(company, year) if period_mode == "annual" else (f"{year}-01-01", f"{year}-06-30")
    return {
        "currency": currency, "revenue": revenue, "gross_profit": gross_value,
        "gross_margin": gross_value / revenue if gross_value is not None and revenue else None,
        "period_start": default_start, "period_end": dates[-1] if dates else default_end,
        "periods": [f"{item_year}/{period}" for item_year, period in sorted(wanted)], "evidence": evidence,
    }


def read_fallback(path: Path | None) -> dict[str, dict[str, str]]:
    if not path:
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result = {}
    for row in rows:
        name = str(row.get("company") or "")
        result[name] = row
        for token in name.replace("/", " ").split():
            if len(token) >= 2:
                result.setdefault(token.lower(), row)
    return result


def fallback_for(key: str, display_name: str, fallback: dict[str, dict[str, str]]) -> dict[str, str] | None:
    return fallback.get(display_name) or fallback.get(key) or fallback.get(key.lower())


def growth_style(rate: float | None) -> tuple[str, str]:
    if rate is None:
        return "", ""
    if rate >= .30: return "优秀", "#38761D"
    if rate >= .20: return "良好", "#6AA84F"
    if rate >= .10: return "一般", "#93C47D"
    if rate >= -.10: return "持平", "#FFFFFF"
    if rate > -.20: return "下滑", "#F4CCCC"
    return "较差", "#EA9999"


def numeric(value: Any) -> float | None:
    if value in (None, "", "未披露"):
        return None
    try:
        return float(str(value).replace(",", "").replace("%", ""))
    except ValueError:
        return None


def silergy_monthly_h1(year: int, source_url: str, raw_dir: Path, session: requests.Session, period_mode: str = "h1") -> tuple[dict[str, Any] | None, str]:
    """Silergy official monthly revenue: June YTD for H1, December YTD for annual."""
    annual = period_mode == "annual"
    target_month = "Dec" if annual else "Jun"
    month_count = 12 if annual else 6
    response = session.get(source_url, params={"year": year}, timeout=30)
    response.raise_for_status()
    raw_path = raw_dir / "official_monthly" / f"Silergy_{year}.html"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(response.text, encoding="utf-8")
    match = re.search(r'<table[^>]+id=["\']monReport["\'][^>]*>(.*?)</table>', response.text, re.I | re.S)
    if not match:
        return None, response.url
    month = ""
    target_usd_ytd = None
    evidence = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", match.group(1), re.I | re.S):
        cells = [
            html.unescape(re.sub(r"<[^>]+>", "", cell)).replace("\xa0", " ").strip()
            for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.I | re.S)
        ]
        if not cells:
            continue
        if cells[0] in {"Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"}:
            month = cells.pop(0)
        if len(cells) >= 5 and cells[0] in {"USD", "NTD"}:
            record = {"month": month, "currency": cells[0], "monthly_k": cells[1], "monthly_yoy": cells[2], "ytd_k": cells[3], "ytd_yoy": cells[4]}
            evidence.append(record)
            if month == target_month and cells[0] == "USD":
                target_usd_ytd = float(cells[3].replace(",", ""))
    if target_usd_ytd is None:
        return None, response.url
    return {
        "currency": "USD", "revenue": target_usd_ytd * 1000, "gross_profit": None, "gross_margin": None,
        "period_start": f"{year}-01-01", "period_end": f"{year}-12-31" if annual else f"{year}-06-30",
        "periods": [f"{year}-{month_index:02d}" for month_index in range(1, month_count + 1)],
        "evidence": evidence,
    }, response.url


def chosen_candidate(eastmoney: dict | None, msn: dict | None, official: dict | None = None) -> tuple[dict | None, str]:
    if eastmoney:
        return eastmoney, "eastmoney_us"
    if msn:
        return msn, "msn_crosscheck"
    if official:
        return official, "official_monthly"
    return None, ""


def relative_difference(left: float, right: float) -> float:
    return abs(left - right) / max(abs(left), abs(right), 1.0)


def fx_for(currency: str, year: int, evidence_dir: Path, cache: dict[tuple[str, int, str], tuple[float, str, str]], period_mode: str = "h1") -> tuple[float, str, str]:
    if currency.upper() == "USD":
        return 1.0, "USD base currency", "identity"
    key = (currency.upper(), year, period_mode)
    if key not in cache:
        period_end = f"{year}-12-31" if period_mode == "annual" else f"{year}-06-30"
        resolved = period_average_usd_per_unit(currency, f"{year}-01-01", period_end, evidence_dir)
        cache[key] = (float(resolved.usd_per_unit), resolved.source_url, resolved.method)
    return cache[key]


def build_row(
    key: str, config: dict[str, Any], target_year: int, compare_year: int,
    target: dict | None, compare: dict | None, target_level: str, compare_level: str,
    sources: dict[str, str], crosscheck_status: str, evidence_dir: Path,
    fx_cache: dict[tuple[str, int, str], tuple[float, str, str]],
    period_mode: str = "h1",
) -> dict[str, Any]:
    display = config.get("display_name") or key
    period_label = (lambda year: f"{year} 年度" if period_mode == "annual" else f"{year} H1")
    row = {field: "" for field in OUTPUT_FIELDS}
    row.update({
        "company": display, "type": "海外", "period_type": "annual" if period_mode == "annual" else "half_year",
        "target_period_label": period_label(target_year), "compare_period_label": period_label(compare_year),
        "target_source_level": target_level, "compare_source_level": compare_level,
        "crosscheck_status": crosscheck_status, "status": "已披露" if target else "未披露",
    })
    converted: dict[str, float | None] = {}
    for role, candidate, year, level in (("target", target, target_year, target_level), ("compare", compare, compare_year, compare_level)):
        if not candidate:
            continue
        currency = str(candidate["currency"]).upper()
        try:
            fx, fx_source, fx_method = fx_for(currency, year, evidence_dir, fx_cache, period_mode)
        except FxRateError as exc:
            raise ValueError(f"{display} {period_label(year)} 汇率获取失败：{exc}") from exc
        local_thousand = float(candidate["revenue"]) / 1000
        usd_thousand = local_thousand * fx
        gross_usd = float(candidate["gross_profit"]) / 1000 * fx if candidate.get("gross_profit") is not None else None
        converted[role] = usd_thousand
        row.update({
            f"{role}_currency": currency, f"{role}_period_start": candidate["period_start"],
            f"{role}_period_end": candidate["period_end"], f"{role}_revenue_local_thousand": round(local_thousand, 3),
            f"{role}_fx_usd_per_unit": fx, f"{role}_fx_source": fx_source, f"{role}_fx_method": fx_method,
            f"{role}_revenue_usd_thousand": round(usd_thousand),
            f"{role}_gross_profit_usd_thousand": round(gross_usd) if gross_usd is not None else "",
            f"{role}_gross_margin": f"{candidate['gross_margin']:.6%}" if candidate.get("gross_margin") is not None else "",
            f"{role}_source": sources.get(f"{role}_{level}", ""),
        })
    target_usd, compare_usd = converted.get("target"), converted.get("compare")
    if target_usd is not None and compare_usd is not None:
        change = target_usd - compare_usd
        rate = change / compare_usd if compare_usd else 0.0
        label, fill = growth_style(rate)
        row.update({"change_usd_thousand": round(change), "growth_rate": f"{rate:.1%}", "growth_label": label, "growth_fill": fill})
    row["notes"] = (
        f"自动取数优先级：东方财富F10→MSN→官网月度/复核CSV；本期={target_level or '未检索到'}，"
        f"上期={compare_level or '未检索到'}；交叉核对={crosscheck_status}"
    )
    return row


def merge_fallback(auto_row: dict[str, Any], fallback: dict[str, str] | None, mode: str) -> dict[str, Any]:
    if not fallback:
        return auto_row
    if mode == "override":
        merged = dict(auto_row)
        merged.update({key: value for key, value in fallback.items() if key in OUTPUT_FIELDS})
        merged["notes"] = (str(merged.get("notes") or "") + "；reviewed_csv_override").strip("；")
        return merged
    if auto_row.get("target_revenue_usd_thousand"):
        return auto_row
    merged = dict(auto_row)
    merged.update({key: value for key, value in fallback.items() if key in OUTPUT_FIELDS})
    merged["notes"] = (str(merged.get("notes") or "") + "；reviewed_csv_fallback").strip("；")
    return merged


def collect(args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    period_mode = period_mode_for(args.target)
    if period_mode_for(args.compare) != period_mode:
        raise ValueError("overseas-fetch 的 target 与 compare 必须属于同一期间类型（同为半年度或同为年度）")
    target_year = int(args.target[:4])
    compare_year = int(args.compare[:4])
    default_keys, companies = load_companies()
    raw_dir = args.raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)
    fallback = read_fallback(args.fallback_normalized_csv)
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 semiconductor-financial-monitor/2.6"})
    fx_cache: dict[tuple[str, int, str], tuple[float, str, str]] = {}
    rows = []
    audit: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"), "target": args.target, "compare": args.compare,
        "period_mode": period_mode,
        "priority": ["eastmoney_us", "msn_crosscheck", "official_monthly", "reviewed_csv", "official_filing"], "companies": {},
    }
    for key in default_keys:
        config = companies[key]
        company_audit: dict[str, Any] = {"display_name": config.get("display_name"), "errors": []}
        sources: dict[str, str] = {}
        eastmoney_by_year: dict[int, dict | None] = {target_year: None, compare_year: None}
        msn_by_year: dict[int, dict | None] = {target_year: None, compare_year: None}
        official_by_year: dict[int, dict | None] = {target_year: None, compare_year: None}
        symbol = config.get("eastmoney_secu_code") or EASTMONEY_SYMBOLS.get(key)
        if symbol and config.get("eastmoney_us_available", True):
            try:
                em_records, em_api_url = eastmoney_records(symbol, raw_dir, session)
                for year in (target_year, compare_year):
                    eastmoney_by_year[year] = extract_eastmoney(key, year, em_records, period_mode)
                    sources[f"{'target' if year == target_year else 'compare'}_eastmoney_us"] = SOURCE_URLS["eastmoney_us"].format(ticker=symbol.split(".")[0])
                company_audit["eastmoney"] = {"symbol": symbol, "api_url": em_api_url, "periods": {str(year): eastmoney_by_year[year] for year in (target_year, compare_year)}}
            except Exception as exc:
                company_audit["errors"].append(f"eastmoney_us: {exc}")
        try:
            quote_id, search_payload = msn_quote_id(key, config, session)
            write_json(raw_dir / "msn" / f"{safe_name(key)}_search.json", search_payload)
            if quote_id:
                msn_records, msn_api_url = msn_financials(quote_id, raw_dir, key, session)
                for year in (target_year, compare_year):
                    msn_by_year[year] = extract_msn(key, year, msn_records, period_mode)
                    sources[f"{'target' if year == target_year else 'compare'}_msn_crosscheck"] = SOURCE_URLS["msn_crosscheck"].format(quote_id=quote_id)
                company_audit["msn"] = {"quote_id": quote_id, "api_url": msn_api_url, "periods": {str(year): msn_by_year[year] for year in (target_year, compare_year)}}
        except Exception as exc:
            company_audit["errors"].append(f"msn_crosscheck: {exc}")

        if key == "Silergy":
            official_url = str(config.get("official_monthly_source_url") or "")
            for year in (target_year, compare_year):
                if msn_by_year[year] is not None or not official_url:
                    continue
                try:
                    official_by_year[year], resolved_url = silergy_monthly_h1(year, official_url, raw_dir, session, period_mode)
                    sources[f"{'target' if year == target_year else 'compare'}_official_monthly"] = resolved_url
                except Exception as exc:
                    company_audit["errors"].append(f"official_monthly {year}: {exc}")
            company_audit["official_monthly"] = {str(year): official_by_year[year] for year in (target_year, compare_year)}

        statuses = []
        for year in (target_year, compare_year):
            em, msn, official = eastmoney_by_year[year], msn_by_year[year], official_by_year[year]
            if em and msn:
                revenue_delta = relative_difference(float(em["revenue"]), float(msn["revenue"])) if em["currency"] == msn["currency"] else math.nan
                statuses.append("matched" if not math.isnan(revenue_delta) and revenue_delta <= args.tolerance else "needs_review")
            elif em or msn or official:
                statuses.append("single_source")
            else:
                statuses.append("missing")
        crosscheck_status = "needs_review" if "needs_review" in statuses else ("missing" if statuses.count("missing") == 2 else "+".join(sorted(set(statuses))))
        target, target_level = chosen_candidate(eastmoney_by_year[target_year], msn_by_year[target_year], official_by_year[target_year])
        compare, compare_level = chosen_candidate(eastmoney_by_year[compare_year], msn_by_year[compare_year], official_by_year[compare_year])
        row = build_row(key, config, target_year, compare_year, target, compare, target_level, compare_level, sources, crosscheck_status, raw_dir / "fx", fx_cache, period_mode)
        row = merge_fallback(row, fallback_for(key, str(config.get("display_name") or key), fallback), args.fallback_mode)
        rows.append(row)
        company_audit["selected"] = {"target": row.get("target_source_level"), "compare": row.get("compare_source_level"), "crosscheck_status": row.get("crosscheck_status")}
        audit["companies"][key] = company_audit

    ranked = sorted((row for row in rows if numeric(row.get("target_revenue_usd_thousand")) is not None), key=lambda row: numeric(row.get("target_revenue_usd_thousand")) or 0, reverse=True)
    for index, row in enumerate(ranked, 1):
        row["rank"] = index
    return rows, audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="Target report date: YYYY-06-30 (H1) or YYYY-12-31 (annual)")
    parser.add_argument("--compare", required=True, help="Comparable report date of the same period type as --target")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--audit-json", required=True, type=Path)
    parser.add_argument("--fallback-normalized-csv", type=Path)
    parser.add_argument("--fallback-mode", choices=["fallback", "override"], default="fallback")
    parser.add_argument("--tolerance", type=float, default=0.01)
    args = parser.parse_args()
    if not 0 <= args.tolerance <= 0.2:
        parser.error("--tolerance must be between 0 and 0.2")
    rows, audit = collect(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    write_json(args.audit_json, audit)
    print(json.dumps({
        "output": str(args.output), "companies": len(rows),
        "disclosed": sum(bool(row.get("target_revenue_usd_thousand")) for row in rows),
        "needs_review": sum(row.get("crosscheck_status") == "needs_review" for row in rows),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
