# Changelog

## v1.0.0 (2026-11-04)

Initial open-source release — full edition, extracted from a production
semiconductor peer-monitoring system.

- **Structured fetch** (`fetch`): Eastmoney US F10 primary source, MSN
  Finance cross-check/fallback, official monthly disclosures and reviewed
  CSV as further fallbacks; raw responses archived; field-level audit JSON.
- **Official-source search & monitoring** (`plan`, `auto`, `monitor`):
  search plans from per-company playbooks, revenue candidate extraction,
  and non-destructive monitoring against reviewed values.
- **Normalization** (`normalize`, `detail-*`): local-currency revenue to
  USD thousands with automatic period-average FX (ECB for EUR/JPY/CNY,
  Taiwan central bank for TWD) and saved rate evidence.
- **Fiscal calendars** for non-calendar fiscal years (Infineon, ADI,
  Microchip, …) across both Eastmoney tokens and MSN fiscal quarters.
- Watchlist externalized to `config/watchlist.json` (10-company
  semiconductor sample included).
- 26 offline tests, all passing.

### Packaging adaptations (extraction notes)

- Modules moved from `scripts/` to `src/`; tests' path bootstrap updated
  accordingly, test logic unchanged.
- Watchlist file renamed from an internal config name to
  `config/watchlist.json`; loader paths updated in four modules.
- `MSN_API_KEY` is read from the environment (no key bundled). When unset,
  MSN calls are skipped with an explicit audit note instead of failing, so
  the F10-primary pipeline still runs — this behavior was verified live
  (TI 2026 H1 revenue matched the vendor figure exactly).
- Domestic (A-share) modules, management-summary decks and global ranking
  from the original system are out of scope here; see finreport-cli for
  A-share reports.
