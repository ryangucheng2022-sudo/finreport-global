# CI kit

Ready-to-enable GitHub Actions setup, kept outside `.github/workflows/`
so it can be reviewed and versioned like any other file.

**Enable it:** copy `ci.yml` to `.github/workflows/ci.yml` and push.

**Scope note:** the job runs the schema-drift contract tests plus the fx,
auto-financials, company-detail and normalize suites. `test_overseas_monitor`
is intentionally excluded: two of its cases read a company-key mapping
config that lives in the operator's environment, not in this repo, and
error without it. Re-include that module here once the config has a
repo-local fixture.
