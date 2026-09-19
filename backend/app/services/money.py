"""Multi-currency money helpers (pure functions, stdlib only).

CURRENCIES maps ISO currency code -> {symbol, locale, decimals}.
`locale` follows Intl-style locale tags and drives digit grouping
(notably en-IN for INR). `format_money` renders e.g. GBP as
"\u00a31,240.00" and INR with en-IN grouping ("\u20b91,00,000.00").
"""

from typing import Dict

CURRENCIES: Dict[str, Dict[str, object]] = {
    "GBP": {"symbol": "\u00a3", "locale": "en-GB", "decimals": 2},
    "USD": {"symbol": "$", "locale": "en-US", "decimals": 2},
    "EUR": {"symbol": "\u20ac", "locale": "en-IE", "decimals": 2},
    "INR": {"symbol": "\u20b9", "locale": "en-IN", "decimals": 2},
    "AED": {"symbol": "AED", "locale": "en-AE", "decimals": 2},
    "AUD": {"symbol": "A$", "locale": "en-AU", "decimals": 2},
    "CAD": {"symbol": "C$", "locale": "en-CA", "decimals": 2},
    "SGD": {"symbol": "S$", "locale": "en-SG", "decimals": 2},
}


def compute_totals(subtotal: float, tax_rate: float) -> dict:
    """Return {subtotal, tax, total}, each rounded to 2dp."""
    sub = round(float(subtotal), 2)
    tax = round(sub * float(tax_rate) / 100.0, 2)
    total = round(sub + tax, 2)
    return {"subtotal": sub, "tax": tax, "total": total}


def _group_standard(int_part: str) -> str:
    groups = []
    while len(int_part) > 3:
        groups.append(int_part[-3:])
        int_part = int_part[:-3]
    groups.append(int_part)
    return ",".join(reversed(groups))


def _group_en_in(int_part: str) -> str:
    # Indian grouping: last 3 digits, then groups of 2 (e.g. 1,00,000).
    if len(int_part) <= 3:
        return int_part
    tail = int_part[-3:]
    head = int_part[:-3]
    groups = []
    while len(head) > 2:
        groups.append(head[-2:])
        head = head[:-2]
    if head:
        groups.append(head)
    return ",".join(reversed(groups)) + "," + tail


def format_money(amount: float, currency: str) -> str:
    """Format `amount` with the currency symbol and locale grouping.

    Unknown currencies fall back to "<CODE> <grouped>" with 2 decimals.
    """
    meta = CURRENCIES.get((currency or "").upper())
    if meta is None:
        code = (currency or "").upper()
        grouped = _group_standard(f"{abs(float(amount)):.2f}".split(".")[0])
        frac = f"{abs(float(amount)):.2f}".split(".")[1]
        sign = "-" if float(amount) < 0 else ""
        return f"{sign}{code} {grouped}.{frac}" if code else f"{sign}{grouped}.{frac}"

    symbol = str(meta["symbol"])
    locale = str(meta["locale"])
    decimals = int(meta["decimals"])
    value = abs(float(amount))
    sign = "-" if float(amount) < 0 else ""
    quantized = f"{value:.{decimals}f}"
    int_part, _, frac_part = quantized.partition(".")
    if locale == "en-IN":
        grouped = _group_en_in(int_part)
    else:
        grouped = _group_standard(int_part)
    number = grouped if decimals == 0 else f"{grouped}.{frac_part}"
    if symbol == "AED":
        return f"{sign}{symbol} {number}"
    return f"{sign}{symbol}{number}"
