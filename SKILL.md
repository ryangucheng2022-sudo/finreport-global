# Skill: finreport-global

Fetch and normalize overseas (non-A-share) peer financials — revenue,
gross profit, gross margin — with dual-source cross-checking and a full
audit trail.

## When to use

The user asks for overseas listed companies' reported revenue/margins for
a quarter, half year or fiscal year; wants a peer comparison in USD; or
needs to check whether an overseas peer has disclosed yet.

## Commands

```bash
bin/finreport-global fetch --target YYYY-06-30|YYYY-12-31 --compare <prior year> \
  --output out.csv --raw-dir raw/ --audit-json audit.json
bin/finreport-global plan|auto|monitor|normalize|detail-validate ... (see README)
```

## Rules

1. Formal disclosures only. Forecasts, guidance and estimates are never
   reported as results; an undisclosed period is labeled 未披露/undisclosed.
2. Respect the source priority (Eastmoney F10 → MSN → official → reviewed
   CSV). When sources disagree beyond tolerance, surface `needs_review`
   with both values — never average or pick silently.
3. Always state the actual fiscal period (start/end dates) for
   non-calendar fiscal-year companies; never present a fiscal quarter as
   if it were a calendar quarter.
4. Quote figures with their source tier (`target_source_level` in the
   output CSV) when reporting to the user.
5. If MSN matters for a company (e.g. Infineon, Renesas) and the audit
   says `MSN_API_KEY not set`, tell the user the MSN route is disabled
   rather than presenting the company as undisclosed.
6. The watchlist is configuration (`config/watchlist.json`); extend it
   instead of hardcoding companies.
