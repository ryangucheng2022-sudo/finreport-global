# finreport-global

English | [简体中文](README.zh-CN.md)

**An overseas peer financial-data engine**: fetch revenue, gross profit and gross margin for non-Chinese listed companies, with two independent structured sources cross-checking each other, fiscal-calendar mapping for non-calendar fiscal years, period-average FX conversion, and field-level source audit — normalized to USD thousands.

Sibling project of [finreport-cli](https://github.com/ryangucheng2022-sudo/finreport-cli) (A-share reports). Extracted from a production peer-monitoring system used for quarterly earnings tracking.

## How it works

```
watchlist.json ──► fetch ──► Eastmoney US F10 (primary, structured)
                      ├──► MSN Finance (cross-check / fallback)
                      ├──► official monthly disclosures (per-company playbook, e.g. Silergy)
                      └──► reviewed CSV (last-resort fallback)
                           │
                           ▼
              standardized CSV (USD thousands) + audit JSON
              (every value carries its source tier and evidence)
```

- **Source priority**: `eastmoney_us` → `msn_crosscheck` → `official_monthly` / `official_filing` → reviewed CSV. Disagreements beyond tolerance are flagged `needs_review`, never silently averaged.
- **Fiscal calendars**: companies like Infineon (FY ends Sep), ADI and Microchip report on fiscal quarters that don't align with calendar quarters. `fiscal_calendar.py` maps both Eastmoney report tokens and MSN fiscal quarters to the real period, and outputs carry the actual period start/end dates.
- **FX**: non-USD figures are converted with period-average rates — ECB daily reference rates for EUR/JPY/CNY, Taiwan central bank interbank data for TWD — with the raw rate evidence saved alongside.
- **Undisclosed means undisclosed**: if no source has formally reported a period, the row says so. Forecasts, guidance and estimates are never substituted.

## Method

- **Primary source.** Eastmoney's US-stock F10 provides structured revenue and margin data — the working source for the peer tables.
- **Cross-check, not blind trust.** MSN Finance figures are compared against the primary source for the same period; where the primary source lacks a period, MSN is the fallback. Disagreements are surfaced in the output, never silently averaged away.
- **Fiscal-calendar mapping.** Fiscal years are mapped to calendar periods per company (a "FY2026" ending in June is not treated as calendar 2026). The mapping is explicit data in the repo, not an assumption in code.
- **Normalization.** Revenue and gross profit are converted to one basis (USD thousands) using dated FX rates, so every company in a table shares the same unit and period definition before any comparison or ranking.
- **Validation.** A per-company detail check re-reads the collected figures against the source plan before a report is assembled.

## Commands

```bash
# Structured fetch for H1 2026 vs H1 2025 (fetch supports 06-30 and 12-31 targets)
bin/finreport-global fetch --target 2026-06-30 --compare 2025-06-30 \
  --output out.csv --raw-dir raw/ --audit-json audit.json

bin/finreport-global plan    --year 2026 --period-type quarter --period 3 --output plan.csv
bin/finreport-global auto    --year 2026 --period-type quarter --period 3 --output candidates.csv
bin/finreport-global monitor --normalized-csv reviewed.csv --year 2026 \
  --period-type quarter --period 3 --output-dir monitor-out/
bin/finreport-global template  --output raw-template.csv
bin/finreport-global normalize --input raw.csv --output normalized.csv
bin/finreport-global detail-template  --output detail-template.csv
bin/finreport-global detail-validate  --input detail.csv
```

- `plan` / `auto`: build official-source search plans and extract revenue candidates from company IR/announcement pages.
- `monitor`: re-check official sources against a reviewed normalized CSV and report what changed — reviewed values are never overwritten automatically.
- `normalize`: turn captured local-currency revenue into USD thousands with automatic period-average FX.

## Configuration

The watchlist is **configuration, not code**: `config/watchlist.json` (a 10-company semiconductor sample ships as `watchlist.example.json`). Each entry carries the Eastmoney security code, legal name, reporting currency, fiscal-year note, primary IR domains and search templates. Add your own companies the same way; per-company quirks (like Silergy's official monthly revenue announcements in TWD with a USD column) live in the playbook docs under `docs/`.

## Who is it for

| Role | Typical scenarios | What you get |
|---|---|---|
| **Cross-border equity research** | Tracking US/EU/JP/TW-listed peers every earnings season | Two structured sources cross-checked per figure, fiscal-period truth instead of calendar assumptions, one USD-thousand table ready for comparison |
| **Strategy & competitive intelligence** | Global peer benchmarking for board materials | Auditable numbers: every value names its source tier, and undisclosed periods are labeled, not estimated |
| **Financial data engineering** | Building a repeatable overseas-filings pipeline | Raw responses archived, FX evidence saved, `needs_review` queue instead of silent bad data — the pipeline is designed to be re-run incrementally |
| **Agent builders** | Letting an AI agent gather peer financials | Deterministic CLI + JSON audit; the agent reports source conflicts rather than hallucinating past them |

## MSN API key

MSN Finance lookups use the public web client key that MSN ships in its own page code. It is **not** bundled: set it via the `MSN_API_KEY` environment variable. Without it, the engine runs on Eastmoney F10 (plus official/reviewed fallbacks) and records `MSN_API_KEY not set` in the audit — for the two sample companies that have no F10 coverage (Infineon, Renesas), MSN is the primary route, so set the key if you need them.

## Data-source disclaimer

Eastmoney F10 and MSN Finance are public web interfaces, not official open APIs; they may change without notice. This project is for research and internal analysis — respect the sources' terms of use. Figures are only as good as the underlying disclosures; the audit trail exists so you can verify them.

## Data-source contracts

Both upstream response shapes are pinned by sanitized fixtures under `tests/fixtures/` and exercised through the real parsers in `tests/test_schema_drift.py`: if Eastmoney or MSN renames a field, the test suite fails rather than a peer table silently emptying. Fixture values are synthetic.

## Requirements & tests

- Python 3.10+, `requests`. Developed on Linux.
- `python3 -m unittest discover -s tests -v` — 26 offline cases (FX math, fiscal mapping, F10/MSN extraction, normalization, monitoring) all passing.

## Version

v1.0.0 — see [CHANGELOG.md](CHANGELOG.md). Packaging notes (what was adapted during extraction) are listed there.

## License

MIT — see [LICENSE](LICENSE).
