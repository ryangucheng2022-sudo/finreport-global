#!/usr/bin/env python3
"""Refresh overseas official-source candidates without bypassing the review gate."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR.parent / "config" / "watchlist.json"
CANDIDATE_FIELDS = [
    "company_key", "company", "period_role", "period_label", "expected_currency",
    "source_url", "candidate_revenue", "candidate_unit", "candidate_currency",
    "confidence", "needs_review", "snippet", "search_query", "notes",
]


def load_company_key_map() -> dict[str, str]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    for key, company in config["companies"].items():
        display = str(company["display_name"])
        mapping[display] = key
        mapping[display.split()[0]] = key
    return mapping


def company_key(name: str, mapping: dict[str, str]) -> str:
    if name in mapping:
        return mapping[name]
    first = str(name).split()[0]
    if first in mapping:
        return mapping[first]
    raise ValueError(f"海外公司无法映射到配置：{name}")


def build_source_map(normalized_csv: Path, output: Path) -> int:
    mapping = load_company_key_map()
    with normalized_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["company_key", "period_role", "source_urls"])
        writer.writeheader()
        for row in rows:
            key = company_key(str(row.get("company") or ""), mapping)
            for role, field in (("target", "target_source"), ("compare", "compare_source")):
                urls = str(row.get(field) or "").strip()
                if urls:
                    writer.writerow({"company_key": key, "period_role": role, "source_urls": urls})
                    count += 1
    return count


def write_timeout_candidates(source_map: Path, output: Path, timeout_seconds: int) -> int:
    """Write review-required rows when the advisory monitor reaches its time budget."""
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    with source_map.open("r", encoding="utf-8-sig", newline="") as handle:
        sources = list(csv.DictReader(handle))
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANDIDATE_FIELDS)
        writer.writeheader()
        for row in sources:
            key = str(row.get("company_key") or "")
            company = config["companies"].get(key, {})
            urls = [item.strip() for item in str(row.get("source_urls") or "").split(";") if item.strip()]
            writer.writerow({
                "company_key": key,
                "company": company.get("display_name", key),
                "period_role": row.get("period_role"),
                "period_label": "",
                "expected_currency": company.get("reporting_currency", ""),
                "source_url": urls[0] if urls else "",
                "candidate_revenue": "",
                "candidate_unit": "",
                "candidate_currency": "",
                "confidence": 0,
                "needs_review": "yes",
                "snippet": "",
                "search_query": "",
                "notes": f"自动监测超过总时限 {timeout_seconds} 秒；保留正式标准化数据并等待人工复核",
            })
    return len(sources)


def summarize_candidates(candidate_csv: Path, output: Path) -> dict:
    with candidate_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("company_key")), str(row.get("period_role")))].append(row)
    summaries = []
    for (key, role), candidates in sorted(grouped.items()):
        best = max(candidates, key=lambda item: int(item.get("confidence") or 0))
        confidence = int(best.get("confidence") or 0)
        ready = bool(best.get("candidate_revenue")) and confidence >= 80 and best.get("needs_review") == "no"
        summaries.append({
            "company_key": key,
            "company": best.get("company"),
            "period_role": role,
            "status": "high_confidence_candidate" if ready else "needs_review",
            "candidate_revenue": best.get("candidate_revenue"),
            "candidate_unit": best.get("candidate_unit"),
            "candidate_currency": best.get("candidate_currency"),
            "confidence": confidence,
            "source_url": best.get("source_url"),
            "notes": best.get("notes"),
        })
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "自动采集只生成官方来源候选，不经复核不得覆盖标准化收入文件",
        "groups": len(summaries),
        "high_confidence_groups": sum(item["status"] == "high_confidence_candidate" for item in summaries),
        "needs_review_groups": sum(item["status"] == "needs_review" for item in summaries),
        "requires_review": any(item["status"] == "needs_review" for item in summaries),
        "results": summaries,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normalized-csv", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--period-type", choices=["quarter", "half_year", "annual"], required=True)
    parser.add_argument("--period", default="1")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    source_map = args.output_dir / "official_source_map.csv"
    candidates = args.output_dir / "overseas_auto_candidates.csv"
    status = args.output_dir / "overseas_monitor_status.json"
    build_source_map(args.normalized_csv, source_map)
    command = [
        sys.executable, str(SCRIPT_DIR / "overseas_auto_collect_revenue.py"),
        "--year", str(args.year), "--period-type", args.period_type, "--period", str(args.period),
        "--workers", str(args.workers),
        "--source-map", str(source_map), "--output", str(candidates),
    ]
    timed_out = False
    try:
        completed = subprocess.run(command, check=False, timeout=args.timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        write_timeout_candidates(source_map, candidates, args.timeout_seconds)
    else:
        if completed.returncode != 0:
            raise SystemExit(completed.returncode)
    payload = summarize_candidates(candidates, status)
    payload["monitor_timed_out"] = timed_out
    payload["timeout_seconds"] = args.timeout_seconds
    status.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "candidate_file": str(candidates.resolve()),
        "status_file": str(status.resolve()),
        "high_confidence_groups": payload["high_confidence_groups"],
        "needs_review_groups": payload["needs_review_groups"],
        "monitor_timed_out": timed_out,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
