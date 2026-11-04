# Company Detail Output Specification

## Purpose

Standardize each overseas company page so cumulative, quarterly, and business-module data remain separate and auditable.

## Workbook Layers

### Cross-company summary

- Use USD K for ranking, share, and combined analysis.
- Keep original currency, original amount, FX, FX source, and conversion formula in the data layer.
- Show source links and actual fiscal-period labels.

### Company page

Use the company's reported currency in thousands:

- USD reporters: `USD K`
- Infineon: `EUR K`
- Renesas: `JPY K`
- Silergy: `NTD K` or the exact currency label used in the filing

Do not convert the company page to USD unless the user explicitly asks for both views.

## Required Page Order

1. `H1 cumulative financial summary`
2. `Quarterly comparison`
3. `Business module / end-market structure`
4. `Business highlights`
5. `Analysis and watch items`
6. `Management outlook`
7. `Official sources`

Each section is a separate visual block. Never place H1, Q1/Q2, and business-module rows in one table.

## Quantitative Tables

### H1 cumulative summary

Columns:

| Metric | Current H1 | Prior-year H1 | YoY / change | Unit | Source |
|---|---:|---:|---:|---|---|

Preferred metrics when disclosed:

- Revenue
- Gross profit
- Gross margin
- Operating income and margin
- Net income
- Diluted EPS
- Operating cash flow / free cash flow

### Quarterly comparison

Columns:

| Metric | Current Q1 | Prior Q1 | Q1 YoY/change | Current Q2 | Prior Q2 | Q2 YoY/change | Unit |
|---|---:|---:|---:|---:|---:|---:|---|

Show the actual fiscal-quarter label and end date in the header or note.

### Business module

Columns:

| Period | Module / end market | Current value | Prior value | YoY | Share | Unit | Source |
|---|---|---:|---:|---:|---:|---|---|

Do not combine modules reported under different periods. Separate Q2 modules from H1 modules when both are available.

## Metric Rules

- `amount`: flow amount; convert to local currency K and allow Q1+Q2 reconciliation.
- `stock`: point-in-time amount; convert to local currency K but never sum Q1 and Q2.
- `rate`: display as percent; compare using percentage-point change.
- `per_share`: retain local currency per share; do not convert to K.
- Loss transitions use status text instead of misleading percentages: `turned profitable`, `turned loss-making`, `loss narrowed`, or `loss widened`.
- Blank and zero are different. Use `未披露` for unavailable values and explain in notes.

## Reconciliation

For consolidated flow amounts when all periods are available:

```text
Current H1 = Current Q1 + Current Q2
Prior H1 = Prior Q1 + Prior Q2
```

Do not apply this formula to rates, per-share values, balance-sheet stocks, or modules whose composition changed.

Gross margin calculation when H1 is not directly disclosed:

```text
H1 gross margin = (Q1 gross profit + Q2 gross profit) / (Q1 revenue + Q2 revenue)
```

Label calculated values and retain both quarter source links.

## Long-Format Detail Dataset

Use `scripts/validate_company_detail.py --write-template ...` to create the expected CSV fields. Important fields:

- `section`: `h1_summary`, `quarter`, or `business_module`
- `period_role`: `H1`, `Q1`, `Q2`, `Q3`, `Q4`, or `FY`
- `dimension`: `consolidated` or an official business-module name
- `metric_type`: `amount`, `stock`, `rate`, or `per_share`
- `unit`: `currency_K`, `percent`, or `currency_per_share`
- `period_current` and `period_compare`: actual reported labels
- `source_current` and `source_compare`: official URLs

## Delivery Checks

- All company-page amounts use local-currency K.
- Summary ranking uses USD K.
- H1, quarterly, and module sections are visually separate.
- Every populated numeric row has official source coverage.
- H1 flow amounts reconcile to Q1+Q2 when all three are present.
- Formula-error scan returns zero.
- All company pages are visually inspected for clipping, overlap, and unreadable text.
