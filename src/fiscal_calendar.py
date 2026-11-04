#!/usr/bin/env python3
"""Explicit calendar/fiscal mappings for overseas peers."""

from __future__ import annotations


COMPANY_FISCAL_NOTES = {
    "ADI": "Natural H1 equals fiscal Q2 + fiscal Q3 under the configured MSN convention.",
    "Infineon": "Fiscal year is offset from calendar year; preserve reported fiscal labels.",
    "Microchip": "Fiscal year is offset from calendar year; preserve reported fiscal labels.",
    "Silergy": "Use calendar months; aggregate Jan-Mar, Apr-Jun, Jul-Sep, Oct-Dec.",
}


def mapping_note(company_key: str) -> str:
    return COMPANY_FISCAL_NOTES.get(company_key, "Use the company's reported fiscal period.")


def calendar_half_months(half: int) -> set[int]:
    if half == 1:
        return {1, 2, 3, 4, 5, 6}
    if half == 2:
        return {7, 8, 9, 10, 11, 12}
    raise ValueError("half must be 1 or 2")


# ---------------------------------------------------------------------------
# Annual (full fiscal year) mapping.
#
# Annual runs use the *full fiscal year* caliber: the four fiscal quarters of
# the fiscal year labelled ``year`` under each source's own labelling
# convention (the same conventions the H1 path already relies on):
# - Calendar-year companies (TI, NXP, STM, onsemi, MPS, Renesas, ...): the
#   fiscal year is the calendar year.
# - ADI / Infineon: MSN and Eastmoney label quarters by fiscal year; the H1
#   path already composes natural H1 from fiscal Q2 + Q3 of that label.
# - Microchip: MSN labels by fiscal year (fiscal Q4 of label Y is calendar
#   Jan-Mar of Y). Eastmoney labels Microchip one year lower than MSN: its
#   H1 tokens for calendar year Y are ``(Y-1)/Q4`` + ``Y/Q1``, i.e. the
#   Eastmoney token year equals the MSN fiscal-year label minus one.
# ---------------------------------------------------------------------------

FISCAL_YEAR_NOTES = {
    "ADI": "Fiscal year ends around the last Saturday of October; annual uses fiscal Q1-Q4 of the labelled fiscal year.",
    "Infineon": "Fiscal year ends September 30; annual uses fiscal Q1-Q4 of the labelled fiscal year.",
    "Microchip": "Fiscal year ends March 31; annual uses fiscal Q1-Q4 of the labelled fiscal year (MSN labels by fiscal year, Eastmoney labels one year lower).",
    "Silergy": "Use calendar months; annual is the December year-to-date figure.",
}


def fiscal_year_note(company_key: str) -> str:
    return FISCAL_YEAR_NOTES.get(
        company_key,
        "Fiscal year equals the calendar year; annual uses calendar Q1-Q4.",
    )


def msn_fiscal_year_quarters(company_key: str, year: int) -> list[tuple[int, str]]:
    """MSN (fiscal-year label, quarter) pairs composing the full fiscal year.

    MSN labels every covered company by fiscal year (see the Microchip note in
    ``overseas_auto_financials.msn_period_types``), so the full fiscal year is
    uniformly Q1-Q4 of the labelled year.
    """
    return [(year, f"q{quarter}") for quarter in range(1, 5)]


def eastmoney_fiscal_year_tokens(company_key: str, year: int) -> list[str]:
    """Eastmoney F10 REPORT tokens composing the full fiscal year.

    Follows the discrete-quarter summation convention already used for
    ADI/Infineon on the H1 path. Microchip tokens sit one year below the MSN
    fiscal-year label, matching its established H1 token pair.
    """
    if company_key == "Microchip":
        return [f"{year - 1}/Q{quarter}" for quarter in range(1, 5)]
    return [f"{year}/Q{quarter}" for quarter in range(1, 5)]


def fiscal_year_bounds(company_key: str, year: int) -> tuple[str, str]:
    """Approximate (start, end) dates of the labelled fiscal year."""
    if company_key == "Microchip":
        return f"{year - 1}-04-01", f"{year}-03-31"
    if company_key == "Infineon":
        return f"{year - 1}-10-01", f"{year}-09-30"
    if company_key == "ADI":
        return f"{year - 1}-11-01", f"{year}-10-31"
    return f"{year}-01-01", f"{year}-12-31"
