"""Shared constants for validation (e.g. country codes)."""
ALLOWED_COUNTRY_CODES = frozenset({'91', '977'})


def normalize_country_code(cc: str) -> str:
    """Strip whitespace and leading '+'; return numeric code (e.g. '+91' -> '91')."""
    if not cc:
        return ''
    s = (cc or '').strip().lstrip('+').strip()
    return s
