"""Caption grammar. Pure functions: text in, structured result or None out.

Grammar is exact per the PRD. Deliberate tolerances (deterministic, never
alter data): keyword case (cash/PayNow/SELL all accepted, stored canonical),
flexible whitespace between tokens, leading/trailing whitespace.
Anything else fails the parse — no guessing.
"""

import re
from decimal import Decimal

from bot.models import Method, MixedCart, Quarantine, SaleLine, SaleType, SingleSale, Trade

# Shared price token: $[total], brackets optional, mismatched brackets invalid.
_PRICE = r"(?:\(\$(?P<amount_b>\d+(?:\.\d{1,2})?)\)|\$(?P<amount>\d+(?:\.\d{1,2})?))"

# [qty]x [item] $[total] [Cash?] [Sell/Buyback?] [note...]
# Brackets around the price are optional — ($[total]) also accepted — but a
# mismatched bracket is not a valid price token and quarantines.
# Defaults (2026-07-18): method defaults to PayNow, sale type defaults to
# Sell — the minimal caption is just "2x p $20". Method may come before or
# after the sale type; typing two conflicting methods fails the parse.
# Trailing free text after the keywords (2026-07-19) becomes the Notes cell
# (e.g. a consignor's name: "1x mew rc $15 cash Sam") — but see
# _note_problem: a note that hides or resembles a keyword quarantines.
_SINGLE_SALE_RE = re.compile(
    r"^(?P<qty>\d+)x\s+(?P<item>.+?)\s+" + _PRICE +
    r"(?:\s+(?P<method_pre>cash|paynow))?"
    r"(?:\s+(?P<type>sell|buyback))?"
    r"(?:\s+(?P<method_post>cash|paynow))?"
    r"(?:[ \t]+(?P<note>\S[^\n]*?))?[ \t]*$",  # note stays on the sale's own line
    re.IGNORECASE,
)

# FR-4: Trade [gave] for [got] ±$[cash] [Cash]
# "+" = customer pays us, "-" = we pay out; omit the money part for an even swap.
# gave/got may not contain "$": an unsigned/misplaced amount must fail the
# parse (and quarantine) rather than be silently absorbed into an item name.
_TRADE_RE = re.compile(
    r"^trade\s+(?P<gave>[^$]+?)\s+for\s+(?P<got>[^$]+?)"
    r"(?:\s+(?P<sign>[+-])\$(?P<cash>\d+(?:\.\d{1,2})?))?"
    r"(?:\s+(?P<method>cash|paynow))?$",
    re.IGNORECASE,
)

# FR-5: cart line — a priced item with no method/type token (implicitly Sell)
_CART_LINE_RE = re.compile(
    r"^(?P<qty>\d+)x\s+(?P<item>.+?)\s+" + _PRICE + r"$",
    re.IGNORECASE,
)

# FR-5: cart total line — the payment, e.g. "$30" or "$30 Cash", with an
# optional trailing note ("$30 Cash Sam"). Item lines carry no note: one
# cart = one row = one Notes cell, so the note rides the payment line.
_CART_TOTAL_RE = re.compile(
    r"^" + _PRICE + r"(?:\s+(?P<method>cash|paynow))?(?:[ \t]+(?P<note>\S[^\n]*?))?[ \t]*$",
    re.IGNORECASE,
)

_METHODS = {"cash": Method.CASH, "paynow": Method.PAYNOW}
_SALE_TYPES = {"sell": SaleType.SELL, "buyback": SaleType.BUYBACK}

_KEYWORDS = ("cash", "paynow", "sell", "buyback")


def _one_typo_apart(a: str, b: str) -> bool:
    """True if a and b are exactly one edit (substitution/insertion/deletion)
    apart. Deterministic guard input — never used to 'fix' anything."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1 :]


def _note_problem(note: str) -> str | None:
    """Free-text notes must not hide money or keywords. A trailing note that
    contains a $ amount, a real keyword, or a one-typo-off keyword is more
    likely a mistyped sale than a note — quarantine it (caught gap beats a
    silently wrong row, e.g. 'buybak' logging as a Sell)."""
    if "$" in note:
        return f'the note "{note}" contains a $ amount — money must come before the note'
    for word in note.split():
        lower = word.lower()
        if lower in _KEYWORDS:
            return (
                f'"{word}" appears after free text — '
                "Cash/PayNow/Sell/Buyback must come before the note"
            )
        for keyword in _KEYWORDS:
            if _one_typo_apart(lower, keyword):
                return f'"{word}" looks like a misspelled "{keyword}" — fix it or reword the note'
    return None

# Item-name short forms (2026-07-18): expanded case-insensitively, whole
# words only, so the sheet always carries the full product name.
_ABBREVIATIONS = {
    "bb": "Booster bundle",
    "p": "Booster pack",
    "etb": "Elite Trainer box",
    "upc": "Ultra premium collection",
    "rc": "Raw card",
    "sb": "Shrinked box",
    "ub": "Unshrinked box",
}


def _expand_item(item: str) -> str:
    return " ".join(_ABBREVIATIONS.get(word.lower(), word) for word in item.split())


# FR-13 groundwork (minimal, deliberately broad): a message is "sale-shaped"
# if any line hints at the grammar — qty-x-item-price, a Trade opener, or a
# price + payment method. Sale-shaped text must parse cleanly or quarantine;
# everything else is ordinary chat and is ignored.
_SALE_SHAPED_RE = re.compile(
    r"(\d+x\s+.*\$\d)|(^\s*trade\s)|(\$\d+(\.\d+)?\s+(cash|paynow))",
    re.IGNORECASE | re.MULTILINE,
)

EXPECTED_FORMATS = (
    "[qty]x [item] $[total] — Sell + PayNow assumed; add Cash and/or Buyback if needed; "
    "any text AFTER the keywords becomes the Notes cell (e.g. an owner's name)\n"
    "Trade [gave] for [got] +$[cash] (customer pays) or -$[cash] (we pay); omit for even\n"
    "mixed cart: one priced line per item ([qty]x [item] $[total]), "
    "then a last line with the payment: $[total] or $[total] Cash [note]"
)


def _matched_amount(match: re.Match) -> str:
    return match["amount_b"] or match["amount"]


def is_sale_shaped(text: str) -> bool:
    return _SALE_SHAPED_RE.search(text) is not None


def parse_message(text: str) -> SingleSale | Trade | MixedCart | Quarantine | None:
    """FR-7 dispatch: a clean parse, a quarantine, or None for ordinary chat."""
    sale = parse_single_sale(text)
    if sale is not None:
        return _note_guarded(sale, text)
    trade = parse_trade(text)
    if trade is not None:
        return trade
    cart = parse_mixed_cart(text)  # MixedCart, or Quarantine on a tie-out failure
    if cart is not None:
        return _note_guarded(cart, text)
    if is_sale_shaped(text):
        return Quarantine(
            raw_text=text,
            reason="Sale-shaped but does not match a known format. Expected one of:\n"
            + EXPECTED_FORMATS,
        )
    return None


def _note_guarded(result, text: str):
    """Quarantine an otherwise-clean parse whose trailing note fails the
    keyword checks (see _note_problem)."""
    if isinstance(result, Quarantine):
        return result
    problem = _note_problem(result.note)
    if problem is None:
        return result
    return Quarantine(raw_text=text, reason="Note check: " + problem)


def parse_single_sale(text: str) -> SingleSale | None:
    """FR-1: parse one Sell/Buyback caption line. None if it doesn't conform."""
    match = _SINGLE_SALE_RE.match(text.strip())
    if match is None:
        return None
    qty = int(match["qty"])
    if qty < 1:
        return None
    if match["method_pre"] and match["method_post"]:
        return None  # two methods typed — ambiguous, never guess
    return SingleSale(
        line=SaleLine(
            qty=qty, item=_expand_item(match["item"]), amount_text=_matched_amount(match)
        ),
        method=_method_or_default(match["method_pre"] or match["method_post"]),
        sale_type=_SALE_TYPES[match["type"].lower()] if match["type"] else SaleType.SELL,
        note=(match["note"] or "").strip(),
    )


def _method_or_default(token: str | None) -> Method:
    return _METHODS[token.lower()] if token else Method.PAYNOW


def parse_trade(text: str) -> Trade | None:
    """FR-4: parse one trade caption. None if it doesn't conform."""
    match = _TRADE_RE.match(text.strip())
    if match is None:
        return None
    return Trade(
        gave=_expand_item(match["gave"]),
        got=_expand_item(match["got"]),
        cash_sign=match["sign"] or "",
        cash_text=match["cash"] or "",
        method=_method_or_default(match["method"]),
    )


def parse_mixed_cart(text: str) -> MixedCart | Quarantine | None:
    """FR-5: priced lines settled by a final total line, one payment.

    Returns None unless every non-blank line conforms (lines implicitly Sell,
    last line the payment). A conforming cart whose lines do not sum exactly
    to the typed total is a Quarantine, never a row (locked decision: the sum
    must tie).
    """
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    total_match = _CART_TOTAL_RE.match(lines[-1])
    if total_match is None:
        return None
    sale_lines = []
    for line in lines[:-1]:
        line_match = _CART_LINE_RE.match(line)
        if line_match is None:
            return None
        qty = int(line_match["qty"])
        if qty < 1:
            return None
        sale_lines.append(
            SaleLine(
                qty=qty,
                item=_expand_item(line_match["item"]),
                amount_text=_matched_amount(line_match),
            )
        )
    total_text = _matched_amount(total_match)
    lines_sum = sum(line.amount for line in sale_lines)
    if lines_sum != Decimal(total_text):
        return Quarantine(
            raw_text=text,
            reason=f"Cart lines sum to ${lines_sum} but the total line says "
            f"${total_text} — the sum must tie exactly.",
        )
    return MixedCart(
        lines=tuple(sale_lines),
        total_text=total_text,
        method=_method_or_default(total_match["method"]),
        note=(total_match["note"] or "").strip(),
    )
