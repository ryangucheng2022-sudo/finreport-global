#!/usr/bin/env python3
"""Auto-search official sources and extract overseas semiconductor revenue candidates.

This script intentionally outputs review-ready candidates instead of silently
claiming final numbers. Overseas disclosures vary by company, fiscal calendar,
currency, PDF layout, and wording; high-confidence candidates can be normalized
after a quick source check.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import ssl
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen


SKILL_DIR = Path(__file__).resolve().parents[1]
CONFIG_CANDIDATES = [
    SKILL_DIR / "config" / "companies.json",
    SKILL_DIR / "config" / "watchlist.json",
]
CONFIG_PATH = next((path for path in CONFIG_CANDIDATES if path.exists()), CONFIG_CANDIDATES[0])

QUARTER_WORDS = {1: "first quarter", 2: "second quarter", 3: "third quarter", 4: "fourth quarter"}
HALF_WORDS = {1: "first half", 2: "second half"}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
}

CURRENCY_SYMBOLS = {
    "$": "USD",
    "US$": "USD",
    "USD": "USD",
    "€": "EUR",
    "EUR": "EUR",
    "JPY": "JPY",
    "¥": "JPY",
    "NT$": "TWD",
    "TWD": "TWD",
}

UNIT_ALIASES = {
    "billion": "billions",
    "billions": "billions",
    "bn": "billions",
    "million": "millions",
    "millions": "millions",
    "mn": "millions",
    "m": "millions",
}

OUT_FIELDS = [
    "company_key",
    "company",
    "period_role",
    "period_label",
    "expected_currency",
    "source_url",
    "candidate_revenue",
    "candidate_unit",
    "candidate_currency",
    "confidence",
    "needs_review",
    "snippet",
    "search_query",
    "notes",
]


@dataclass
class SearchPlan:
    company_key: str
    company: dict
    period_role: str
    year: int
    period_type: str
    period: str
    period_label: str
    query: str


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def period_words(period_type: str, period: str) -> str:
    if period_type == "annual":
        return "full year"
    n = int(period)
    if period_type == "half_year":
        return HALF_WORDS[n]
    return QUARTER_WORDS[n]


def period_label(year: int, period_type: str, period: str) -> str:
    if period_type == "annual":
        return f"{year} full year"
    n = int(period)
    if period_type == "half_year":
        return f"{year} H{n}"
    return f"{year} Q{n}"


def fiscal_period(company_key: str, year: int, period_type: str, period: str) -> tuple[str, int]:
    if period_type == "annual":
        return "full year", year
    n = int(period)
    if company_key == "Infineon" and period_type == "quarter":
        fiscal_q = {1: 2, 2: 3, 3: 4, 4: 1}[n]
        return f"Q{fiscal_q}", year if n in (1, 2, 3) else year + 1
    if company_key == "Microchip" and period_type == "quarter":
        fiscal_q = {1: 4, 2: 1, 3: 2, 4: 3}[n]
        return f"Q{fiscal_q}", year if n == 1 else year + 1
    if company_key == "ADI" and period_type == "quarter":
        fiscal_q = {1: 2, 2: 3, 3: 4, 4: 1}[n]
        return f"Q{fiscal_q}", year if n in (1, 2, 3) else year + 1
    return period_words(period_type, period), year


def build_search_plan(company_key: str, company: dict, role: str, year: int, period_type: str, period: str) -> SearchPlan:
    fiscal_label, fiscal_year = fiscal_period(company_key, year, period_type, period)
    template = company["query_templates"][period_type]
    query = template.format(
        year=year,
        period_label=period_words(period_type, period),
        fiscal_period_label=fiscal_label,
        fiscal_year=fiscal_year,
    )
    return SearchPlan(
        company_key=company_key,
        company=company,
        period_role=role,
        year=year,
        period_type=period_type,
        period=period,
        period_label=period_label(year, period_type, period),
        query=query,
    )


def fetch_url(url: str, timeout: int = 20) -> bytes:
    request = Request(url, headers=HEADERS)
    context = ssl._create_unverified_context()
    with urlopen(request, timeout=timeout, context=context) as response:
        return response.read()


def unwrap_duckduckgo_url(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if "uddg" in query:
        return unquote(query["uddg"][0])
    return url


def search_official_urls(query: str, domains: list[str], max_results: int = 4) -> list[str]:
    urls: list[str] = []
    for domain in domains:
        search_url = f"https://duckduckgo.com/html/?q={quote_plus(query + ' site:' + domain)}"
        try:
            text = fetch_url(search_url).decode("utf-8", errors="ignore")
        except Exception:
            continue
        hrefs = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"', text)
        hrefs += re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(?:[^<]|<[^a])*?</a>', text)
        for href in hrefs:
            candidate = html.unescape(unwrap_duckduckgo_url(href))
            host = urlparse(candidate).netloc.lower()
            if any(domain.lower() in host for domain in domains) and candidate not in urls:
                urls.append(candidate)
            if len(urls) >= max_results:
                return urls
        time.sleep(0.2)
    return urls


def html_to_text(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="ignore")
    text = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", text)
    text = re.sub(r"(?is)<br\\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p|</div|</tr|</li", "\n<", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    return normalize_text(text)


def pdf_to_text(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return ""
    try:
        reader = PdfReader(BytesIO(raw))
        parts = [(page.extract_text() or "") for page in reader.pages[:8]]
        return normalize_text("\n".join(parts))
    except Exception:
        return ""


def normalize_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text_from_url(url: str) -> str:
    raw = fetch_url(url)
    if ".pdf" in urlparse(url).path.lower() or raw[:4] == b"%PDF":
        text = pdf_to_text(raw)
        if text:
            return text
    return html_to_text(raw)


def currency_regex(expected_currency: str) -> str:
    symbols = [re.escape(k) for k, v in CURRENCY_SYMBOLS.items() if v == expected_currency]
    if not symbols:
        return r"(?:US\\$|\\$|€|EUR|USD|JPY|¥|NT\\$|TWD)?"
    return r"(?:" + "|".join(symbols) + r")?"


def revenue_candidates(text: str, expected_currency: str) -> list[dict]:
    keywords = r"(?:net\s+revenues?|revenues?|net\s+sales|sales|turnover)"
    cur = currency_regex(expected_currency)
    number = r"([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)"
    unit = r"(billion|billions|million|millions|bn|mn|m)"
    patterns = [
        re.compile(rf"(?is)({keywords}.{{0,140}}?{cur}\s*{number}\s*{unit})"),
        re.compile(rf"(?is)({cur}\s*{number}\s*{unit}.{{0,140}}?{keywords})"),
        re.compile(rf"(?is)({keywords}.{{0,80}}?{number}\s*{unit}.{{0,40}}?(?:{expected_currency}|euros?|yen|dollars?))"),
    ]
    candidates: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for pattern in patterns:
        for match in pattern.finditer(text):
            start = max(0, match.start(1) - 120)
            end = min(len(text), match.end(1) + 160)
            snippet = normalize_text(text[start:end])
            phrase = normalize_text(match.group(1))
            values = re.findall(rf"{cur}\s*{number}\s*{unit}", phrase, flags=re.I)
            if not values:
                values = re.findall(rf"{number}\s*{unit}", phrase, flags=re.I)
            if not values:
                continue
            raw_value, raw_unit = values[0][0], values[0][1]
            key = (raw_value, raw_unit.lower())
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                {
                    "candidate_revenue": raw_value.replace(",", ""),
                    "candidate_unit": UNIT_ALIASES.get(raw_unit.lower(), raw_unit.lower()),
                    "candidate_currency": expected_currency,
                    "snippet": snippet[:500],
                }
            )
    return candidates


def score_candidate(candidate: dict, source_url: str) -> int:
    score = 50
    snippet = candidate["snippet"].lower()
    if "reported" in snippet and "revenue" in snippet:
        score += 20
    if "net revenue" in snippet or "net revenues" in snippet:
        score += 20
    if "revenue" in snippet:
        score += 15
    if "quarter" in snippet or "year" in snippet or "six months" in snippet:
        score += 10
    if ".pdf" in urlparse(source_url).path.lower():
        score += 5
    if "free cash flow" in snippet or "% of revenue" in snippet or "percentage of revenue" in snippet:
        score -= 35
    if "outlook" in snippet or "range of" in snippet or "revenue in the range" in snippet:
        score -= 45
    try:
        value = float(candidate.get("candidate_revenue", 0))
        unit = candidate.get("candidate_unit", "")
        if unit == "millions" and value < 1000:
            score -= 20
    except Exception:
        pass
    return max(0, min(100, score))


def collect_for_plan(plan: SearchPlan, source_urls: list[str], max_results: int) -> list[dict]:
    domains = plan.company["primary_domains"]
    urls = source_urls or search_official_urls(plan.query, domains, max_results=max_results)
    rows: list[dict] = []
    if not urls:
        rows.append(empty_row(plan, "未找到官方候选链接"))
        return rows
    for url in urls:
        try:
            text = extract_text_from_url(url)
        except Exception as exc:
            rows.append(empty_row(plan, f"下载失败: {exc}", url))
            continue
        candidates = revenue_candidates(text, plan.company["reporting_currency"])
        if not candidates:
            rows.append(empty_row(plan, "未自动识别收入候选值", url))
            continue
        for candidate in candidates[:5]:
            confidence = score_candidate(candidate, url)
            rows.append(
                {
                    "company_key": plan.company_key,
                    "company": plan.company["display_name"],
                    "period_role": plan.period_role,
                    "period_label": plan.period_label,
                    "expected_currency": plan.company["reporting_currency"],
                    "source_url": url,
                    "candidate_revenue": candidate["candidate_revenue"],
                    "candidate_unit": candidate["candidate_unit"],
                    "candidate_currency": candidate["candidate_currency"],
                    "confidence": confidence,
                    "needs_review": "no" if confidence >= 80 else "yes",
                    "snippet": candidate["snippet"],
                    "search_query": plan.query,
                    "notes": plan.company["fiscal_note"],
                }
            )
    rows.sort(key=lambda row: int(row.get("confidence") or 0), reverse=True)
    return rows


def empty_row(plan: SearchPlan, note: str, url: str = "") -> dict:
    return {
        "company_key": plan.company_key,
        "company": plan.company["display_name"],
        "period_role": plan.period_role,
        "period_label": plan.period_label,
        "expected_currency": plan.company["reporting_currency"],
        "source_url": url,
        "candidate_revenue": "",
        "candidate_unit": "",
        "candidate_currency": "",
        "confidence": 0,
        "needs_review": "yes",
        "snippet": "",
        "search_query": plan.query,
        "notes": note,
    }


def write_rows(rows: list[dict], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def source_map(path: Path | None) -> dict[tuple[str, str], list[str]]:
    if not path:
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        result: dict[tuple[str, str], list[str]] = {}
        for row in rows:
            key = (row["company_key"], row.get("period_role", "target"))
            urls = [u.strip() for u in row.get("source_urls", "").split(";") if u.strip()]
            if urls:
                result[key] = urls
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--period-type", choices=["quarter", "half_year", "annual"], required=True)
    parser.add_argument("--period", default="1")
    parser.add_argument("--compare-year", type=int, help="Default: year - 1")
    parser.add_argument("--companies", nargs="*", help="Company keys from config")
    parser.add_argument("--source-map", type=Path, help="Optional CSV: company_key,period_role,source_urls")
    parser.add_argument("--max-search-results", type=int, default=3)
    parser.add_argument("--workers", type=int, default=4, help="Parallel company-period checks (1-10)")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    config = load_config()
    company_keys = args.companies or config["default_companies"]
    compare_year = args.compare_year or args.year - 1
    provided_sources = source_map(args.source_map)

    if not 1 <= args.workers <= 10:
        parser.error("--workers must be between 1 and 10")

    tasks: list[tuple[SearchPlan, list[str]]] = []
    for company_key in company_keys:
        company = config["companies"][company_key]
        for role, year in [("target", args.year), ("compare", compare_year)]:
            plan = build_search_plan(company_key, company, role, year, args.period_type, args.period)
            urls = provided_sources.get((company_key, role), [])
            tasks.append((plan, urls))

    def collect(task: tuple[SearchPlan, list[str]]) -> list[dict]:
        plan, urls = task
        result = collect_for_plan(plan, urls, max_results=args.max_search_results)
        time.sleep(0.1)
        return result

    rows: list[dict] = []
    # Preserve deterministic task order while bounding network concurrency.
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for collected in executor.map(collect, tasks):
            rows.extend(collected)

    write_rows(rows, args.output)
    print(f"Wrote {len(rows)} auto-collected candidate rows to {args.output}")


if __name__ == "__main__":
    main()
