# Overseas Semiconductor Revenue Procedure

## Goal

Produce traceable quarterly, half-year, or annual financial data for overseas semiconductor peers. Use USD thousands for cross-company comparison and local-currency thousands for company detail pages. Every populated value must retain official source coverage.

## Required Inputs

- Company list, or use `config/companies.json` defaults.
- Period type:
  - `quarter`
  - `half_year`
  - `annual`
- Target year and period number:
  - Quarter: `1`, `2`, `3`, `4`
  - Half-year: `1`, `2`
  - Annual: omit or use `full_year`
- Compare period. Default is prior-year same period.
- Output unit. Default: `USD thousands`.
- Company-page output. Default: local reported currency in thousands.

## Source Priority

Use sources in this order:

1. 东方财富美股 F10 structured financial interface, where coverage exists; retain raw field identifiers and amount.
2. MSN Finance when F10 has no data, or as a cross-check; record page currency and send discrepancies to review.
3. Company IR press release, annual/interim report PDF, SEC EDGAR, or stock-exchange filing when the prior sources are unavailable or inconsistent.
4. Reputable wire copy only when it reproduces the official company release and the official site is unreachable. Flag this in notes.

Do not use:

- Search result snippets as source.
- Analyst forecasts as actual revenue.
- Unverified market-data summaries. MSN is permitted only under the controlled priority rule above.
- Unsourced database summaries.

## Data Capture Fields

Capture one row per company and period pair:

| Field | Description |
|---|---|
| company | Standard company display name |
| period_type | quarter / half_year / annual |
| target_period_label | Actual reported period, e.g. `2026 Q1`, `FY2026 Q2`, `six months ended Jun 30 2026` |
| compare_period_label | Prior-year same period |
| target_period_start / target_period_end | Exact start/end dates of target flow period; required when using automatic FX |
| target_revenue | Numeric original reported revenue |
| target_unit | ones / thousands / millions / billions |
| target_currency | USD / EUR / JPY / TWD / other ISO code |
| target_source | Official URL |
| compare_revenue | Numeric original reported revenue |
| compare_unit | ones / thousands / millions / billions |
| compare_currency | Currency |
| compare_source | Official URL |
| target_fx_usd_per_unit | USD per 1 unit of target currency |
| target_fx_source | Populated automatically from ECB or supplied with a manual override |
| compare_fx_usd_per_unit | USD per 1 unit of compare currency |
| compare_period_start / compare_period_end | Exact start/end dates of compare flow period; required when using automatic FX |
| compare_fx_source | Populated automatically from ECB or supplied with a manual override |
| notes | Fiscal-year mapping, manual calculation notes, source caveats |

The normalized revenue output must retain both local-currency-thousand and USD-thousand values. For detailed company-page metrics, use the long-format schema in `COMPANY_DETAIL_OUTPUT_SPEC.md` and validate it with `scripts/validate_company_detail.py`.

## Period Mapping Rules

### Calendar-Year Reporters

For TI, NXP, STM, Renesas, onsemi, MPS, and most Taiwan monthly revenue tables:

- Quarter 1: January to March
- Quarter 2: April to June
- Quarter 3: July to September
- Quarter 4: October to December
- Half 1: Q1 + Q2, or first six months
- Half 2: Q3 + Q4, or second six months
- Annual: January to December

### Fiscal-Year-Misaligned Reporters

Always disclose the actual fiscal period used.

- Infineon: fiscal year ends September 30. Calendar Q1 usually maps to FY Q2.
- Microchip: fiscal year ends March 31. Calendar Q1 usually maps to FY Q4.
- ADI: fiscal year ends around late October/early November. There is no exact calendar-Q1 quarter; use the closest reported fiscal quarter only when the user accepts this approximation, and write the exact quarter end date.

If the user demands strict calendar-year months and a company does not report by calendar quarter, use monthly revenue disclosures if available; otherwise state that strict calendar data is unavailable from public filings.

## FX Rules

Default output is USD thousands.

- USD source: `fx = 1`.
- EUR, JPY and CNY: leave `*_fx_usd_per_unit` blank and provide the actual `*_period_start`/`*_period_end`; the standardizer retrieves ECB daily reference rates, calculates a same-period arithmetic average, and archives the raw CSV plus calculation record.
- TWD: retrieve daily NTD/USD interbank closing rates from the Central Bank of the Republic of China (Taiwan), convert to USD per TWD, calculate the period arithmetic average, and retain the raw response. Any other uncovered currency requires a reviewed rate and source URL.
- A filled `*_fx_usd_per_unit` is an explicit manual override and must retain its source URL.
- Formula:

```text
Revenue USD thousands = revenue_original * unit_multiplier * fx_usd_per_unit / 1,000
```

Unit multipliers:

- ones: `1`
- thousands: `1,000`
- millions: `1,000,000`
- billions: `1,000,000,000`

Default FX sources are the ECB EXR API for EUR/JPY/CNY and the Taiwan central-bank open-data API for TWD. Company-provided USD equivalents may be used only when the company explicitly reports them.

FX conversion applies to the cross-company summary. Company pages retain local currency and normalize only the unit to thousands.

## Half-Year Construction

If a company reports H1 directly, use that number.

If only quarters are disclosed:

1. Sum Q1 and Q2 for H1.
2. Sum Q3 and Q4 for H2.
3. Preserve both quarter source links.
4. Add `calculated from quarterly releases` to notes.

Only flow amounts may be added. Do not add gross margin, operating margin, EPS, accounts receivable, accounts payable, inventory, cash, or other point-in-time balances. Derive H1 margins from the corresponding H1 numerator and denominator only when direct disclosure is unavailable, and label the result as calculated.

## Quality Checklist

Before delivering:

- Every row has a source URL.
- Every non-USD row has FX and FX source.
- Period labels match actual fiscal/calendar period.
- YoY uses same period basis.
- Units are not mixed: millions vs billions vs thousands checked.
- Totals match row sums.
- Growth percentage is recomputed from USD values unless the user explicitly asks to preserve source-reported local-currency YoY.
- Any unavailable data is marked `未披露` rather than guessed.
- Company pages separate H1 cumulative, quarterly, and business-module tables.
- Every company-page amount uses the company's local-currency K unit.
- Consolidated H1 flow amounts equal Q1 + Q2 when all three periods are present.
- Ratios use percentage-point changes; stock metrics are not summed.
- Workbook formula scan and page-by-page visual review pass before delivery.
