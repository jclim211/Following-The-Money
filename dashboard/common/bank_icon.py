"""Neutral bank emblem shared by the BQ1 pages.

The dataset's banks are synthetic (IBM AML), so there are no real logos.
One neutral icon plus the bank name and id keeps rows easy to scan.
"""
from urllib.parse import quote

_BANK_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48">
<rect width="48" height="48" rx="10" fill="#6B7280"/>
<path d="M7 18 24 8l17 10v3H7v-3Zm4 6h5v12h-5V24Zm10.5 0h5v12h-5V24ZM32 24h5v12h-5V24ZM7 39h34v4H7v-4Z" fill="#FFFFFF"/>
</svg>"""
BANK_ICON_DATA_URL = "data:image/svg+xml;utf8," + quote(_BANK_ICON_SVG)


def bank_label(name, bank_id) -> str:
    """Bank names are not unique (two 'Future Savings Bank'), so always show the id."""
    return f"{name or 'unknown'} ({bank_id})"
