"""Domain types. Money is carried as the exact typed string (FR-2);
Decimal views are derived for arithmetic, never stored back."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class Method(Enum):
    CASH = "Cash"
    PAYNOW = "PayNow"


class SaleType(Enum):
    SELL = "Sell"
    BUYBACK = "Buyback"


@dataclass(frozen=True)
class SaleLine:
    qty: int
    item: str
    amount_text: str  # exactly as typed, e.g. "113.30" — never reformatted

    @property
    def amount(self) -> Decimal:
        return Decimal(self.amount_text)


@dataclass(frozen=True)
class Trade:
    """FR-4: swap of goods with an optional signed cash top-up.
    "+" = customer pays us, "-" = we pay the customer."""

    gave: str
    got: str
    cash_sign: str  # "+", "-", or "" for an even trade
    cash_text: str  # exactly as typed; "" for an even trade
    method: Method
    note: str = ""  # trailing free text (e.g. consignor name) -> Notes column

    @property
    def cash_delta(self) -> Decimal:
        if not self.cash_text:
            return Decimal("0")
        amount = Decimal(self.cash_text)
        return -amount if self.cash_sign == "-" else amount


@dataclass(frozen=True)
class MixedCart:
    """FR-5: several priced Sell lines settled as one payment.
    Only constructed when the lines tie exactly to the typed total."""

    lines: tuple[SaleLine, ...]
    total_text: str  # exactly as typed
    method: Method
    note: str = ""  # trailing free text on the total line -> Notes column

    @property
    def total(self) -> Decimal:
        return Decimal(self.total_text)


@dataclass(frozen=True)
class Quarantine:
    """FR-7: sale-shaped text that failed to parse cleanly. Never written as a row."""

    raw_text: str
    reason: str


@dataclass(frozen=True)
class SingleSale:
    line: SaleLine
    method: Method
    sale_type: SaleType
    note: str = ""  # trailing free text (e.g. consignor name) -> Notes column

    @property
    def cash_delta(self) -> Decimal:
        """Signed till movement: Sell = cash in, Buyback = cash out (FR-1)."""
        sign = 1 if self.sale_type is SaleType.SELL else -1
        return sign * self.line.amount
