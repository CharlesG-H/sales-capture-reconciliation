from decimal import Decimal

import pytest

from bot.models import Method, MixedCart, Quarantine, SaleType, SingleSale, Trade
from bot.parser import parse_message, parse_mixed_cart, parse_single_sale, parse_trade


class TestSingleSaleHappyPath:
    def test_basic_cash_sell(self):
        sale = parse_single_sale("1x gold case ($10) Cash Sell")
        assert sale.line.qty == 1
        assert sale.line.item == "gold case"
        assert sale.line.amount_text == "10"
        assert sale.method is Method.CASH
        assert sale.sale_type is SaleType.SELL

    def test_paynow_buyback(self):
        sale = parse_single_sale("3x Evolving Skies pack ($9.60) PayNow Buyback")
        assert sale.line.qty == 3
        assert sale.line.item == "Evolving Skies pack"
        assert sale.line.amount_text == "9.60"
        assert sale.method is Method.PAYNOW
        assert sale.sale_type is SaleType.BUYBACK

    def test_item_may_contain_parens_and_digits(self):
        sale = parse_single_sale("1x PSA10 Charizard (base set) ($450.50) PayNow Sell")
        assert sale.line.item == "PSA10 Charizard (base set)"
        assert sale.line.amount_text == "450.50"

    def test_keywords_case_insensitive_stored_canonical(self):
        sale = parse_single_sale("2x pack ($5) cash SELL")
        assert sale.method.value == "Cash"
        assert sale.sale_type.value == "Sell"

    def test_qty_x_case_insensitive_item_casing_preserved(self):
        sale = parse_single_sale("1X MEW $120 PAYNOW SELL")
        assert sale.line.qty == 1
        assert sale.line.item == "MEW"  # item keeps typed casing
        assert sale.method.value == "PayNow"

    def test_omitted_method_defaults_to_paynow(self):
        sale = parse_single_sale("1x mew $120 Sell")
        assert sale.method is Method.PAYNOW
        assert sale.sale_type is SaleType.SELL

    def test_minimal_caption_defaults_to_paynow_sell(self):
        sale = parse_single_sale("2x p $20")
        assert sale.line.item == "Booster pack"
        assert sale.method is Method.PAYNOW
        assert sale.sale_type is SaleType.SELL

    def test_bare_caption_with_cash_only(self):
        sale = parse_single_sale("1x gold case ($10) Cash")
        assert sale.method is Method.CASH
        assert sale.sale_type is SaleType.SELL

    def test_method_accepted_after_sale_type(self):
        sale = parse_single_sale("1x mew $120 sell cash")
        assert sale.method is Method.CASH
        assert sale.sale_type is SaleType.SELL

    def test_buyback_with_trailing_method(self):
        sale = parse_single_sale("1x zard psa9 $80 buyback cash")
        assert sale.method is Method.CASH
        assert sale.sale_type is SaleType.BUYBACK

    def test_cash_must_be_stated(self):
        sale = parse_single_sale("1x mew $120 Cash Buyback")
        assert sale.method is Method.CASH

    def test_explicit_paynow_still_accepted(self):
        assert parse_single_sale("1x mew $120 PayNow Sell").method is Method.PAYNOW

    def test_bare_price_without_brackets(self):
        sale = parse_single_sale("1x mew $120 PayNow Sell")
        assert sale.line.item == "mew"
        assert sale.line.amount_text == "120"
        assert sale.method is Method.PAYNOW

    def test_bare_price_keeps_typed_decimals(self):
        sale = parse_single_sale("3x Evolving Skies pack $9.60 Cash Buyback")
        assert sale.line.amount_text == "9.60"

    def test_flexible_internal_whitespace(self):
        assert parse_single_sale("1x  gold case  ($10)  Cash  Sell") is not None

    def test_leading_trailing_whitespace(self):
        assert parse_single_sale("  1x gold case ($10) Cash Sell  ") is not None


class TestMoneyExactness:
    """FR-2: the stored figure is the typed figure, character for character."""

    @pytest.mark.parametrize("typed", ["113.30", "5", "5.5", "0.50", "1000.01"])
    def test_amount_text_is_verbatim(self, typed):
        sale = parse_single_sale(f"1x pack (${typed}) Cash Sell")
        assert sale.line.amount_text == typed

    def test_decimal_view_matches_text(self):
        sale = parse_single_sale("1x pack ($113.30) Cash Sell")
        assert sale.line.amount == Decimal("113.30")

    def test_buyback_cash_delta_is_negative(self):
        sale = parse_single_sale("1x pack ($10) Cash Buyback")
        assert sale.cash_delta == Decimal("-10")

    def test_sell_cash_delta_is_positive(self):
        sale = parse_single_sale("1x pack ($10) Cash Sell")
        assert sale.cash_delta == Decimal("10")


class TestSingleSaleRejections:
    """FR-7 groundwork: anything non-conforming returns None, never a guess."""

    @pytest.mark.parametrize(
        "text",
        [
            "gold case ($10) Cash Sell",            # no qty
            "0x gold case ($10) Cash Sell",         # zero qty
            "1x gold case ($10 Cash Sell",          # mismatched opening bracket
            "1x gold case $10) Cash Sell",          # mismatched closing bracket
            "1x gold case ($10) Cash Sell PayNow",  # two methods — ambiguous
            "1x gold case ($1,000) Cash Sell",      # comma in amount
            "1x gold case ($10.999) Cash Sell",     # >2 decimal places
            "1x gold case ($-10) Cash Sell",        # negative amount
            "sold two packs for ten bucks cash",    # free text
            "",
        ],
    )
    def test_rejects(self, text):
        assert parse_single_sale(text) is None


class TestItemAbbreviations:
    """Short forms expand to full product names, case-insensitively."""

    @pytest.mark.parametrize(
        ("typed", "expanded"),
        [
            ("BB", "Booster bundle"),
            ("bb", "Booster bundle"),
            ("P", "Booster pack"),
            ("etb", "Elite Trainer box"),
            ("UPC", "Ultra premium collection"),
            ("rc", "Raw card"),
            ("SB", "Shrinked box"),
            ("ub", "Unshrinked box"),
        ],
    )
    def test_whole_item_short_form(self, typed, expanded):
        assert parse_single_sale(f"2x {typed} $220 Sell").line.item == expanded

    def test_expands_within_item_name(self):
        sale = parse_single_sale("1x AH bb $110 Sell")
        assert sale.line.item == "AH Booster bundle"

    def test_box_codes_follow_any_set_name(self):
        assert parse_single_sale("1x abyss eye sb $60").line.item == "abyss eye Shrinked box"
        assert parse_single_sale("1x 151 ub $180").line.item == "151 Unshrinked box"

    def test_only_whole_words_expand(self):
        assert parse_single_sale("1x UPCA $5 Sell").line.item == "UPCA"

    def test_cart_lines_expand(self):
        cart = parse_mixed_cart("2x p $9\n1x ETB $55\n$64")
        assert cart.lines[0].item == "Booster pack"
        assert cart.lines[1].item == "Elite Trainer box"

    def test_trade_sides_expand(self):
        trade = parse_trade("Trade etb for upc +$30")
        assert trade.gave == "Elite Trainer box"
        assert trade.got == "Ultra premium collection"


class TestTrade:
    """FR-4: Trade [gave] for [got] ±$[cash] [Cash]."""

    def test_customer_tops_up(self):
        trade = parse_trade("Trade PSA9 Zard for PSA10 Pika +$50 Cash")
        assert trade.gave == "PSA9 Zard"
        assert trade.got == "PSA10 Pika"
        assert trade.cash_sign == "+"
        assert trade.cash_text == "50"
        assert trade.method is Method.CASH
        assert trade.cash_delta == Decimal("50")

    def test_we_pay_out(self):
        trade = parse_trade("Trade PSA10 Pika for PSA9 Zard -$30.50")
        assert trade.cash_delta == Decimal("-30.50")
        assert trade.method is Method.PAYNOW  # default when omitted

    def test_even_trade_no_money(self):
        trade = parse_trade("Trade slab A for slab B")
        assert trade.cash_text == ""
        assert trade.cash_delta == Decimal("0")

    def test_case_insensitive(self):
        assert parse_trade("TRADE a FOR b +$1 CASH") is not None

    @pytest.mark.parametrize(
        "text",
        [
            "Trade PSA9 Zard PSA10 Pika +$50",   # missing "for"
            "Trade for PSA10 Pika",              # missing gave
            "Trade PSA9 Zard for PSA10 $50",     # unsigned cash: sign is required
            "Traded my Zard for a Pika",         # "Traded" is not the opener
        ],
    )
    def test_rejects(self, text):
        assert parse_trade(text) is None

    def test_malformed_trade_quarantines(self):
        assert isinstance(parse_message("Trade PSA9 Zard for PSA10 $50"), Quarantine)


class TestMixedCart:
    """FR-5: priced lines + a final total line; the sum must tie exactly."""

    def test_two_line_cart(self):
        cart = parse_mixed_cart("2x pack $20\n1x case $10\n$30")
        assert len(cart.lines) == 2
        assert cart.lines[0].item == "pack"
        assert cart.total_text == "30"
        assert cart.method is Method.PAYNOW  # default when omitted

    def test_cash_total_line(self):
        cart = parse_mixed_cart("2x pack $20\n1x case $10\n$30 Cash")
        assert cart.method is Method.CASH

    def test_blank_lines_tolerated(self):
        cart = parse_mixed_cart("1x Pika 151 AR ($150.32)\n1x Slowpoke AR ($88.70)\n\n$239.02")
        assert cart is not None
        assert cart.total_text == "239.02"

    def test_amounts_verbatim(self):
        cart = parse_mixed_cart("1x pack $9.60\n1x case $10\n$19.60")
        assert cart.lines[0].amount_text == "9.60"
        assert cart.total_text == "19.60"

    def test_total_ties_across_decimal_forms(self):
        # Decimal comparison: 20 + 10.00 ties to a typed "$30"
        assert isinstance(parse_mixed_cart("2x pack $20\n1x case $10.00\n$30"), MixedCart)

    def test_sum_mismatch_quarantines(self):
        result = parse_mixed_cart("2x pack $20\n1x case $10\n$35")
        assert isinstance(result, Quarantine)
        assert "sum to $30" in result.reason
        assert "says $35" in result.reason

    def test_mismatch_quarantines_via_dispatch(self):
        assert isinstance(parse_message("2x pack $20\n1x case $10\n$35"), Quarantine)

    @pytest.mark.parametrize(
        "text",
        [
            "$30",                                   # total line alone
            "2x pack $20\n1x case $10",              # no total line
            "2x pack $20 Sell\n$20",                 # cart lines must not carry Sell/Buyback
            "Claimed\n1x pack $20\n$20",             # leading free-text line
        ],
    )
    def test_non_conforming_returns_none(self, text):
        assert parse_mixed_cart(text) is None


class TestParseMessageDispatch:
    """FR-7: clean parse → sale; sale-shaped mess → quarantine; chat → ignored."""

    def test_clean_sale_parses(self):
        assert isinstance(parse_message("1x gold case ($10) Cash Sell"), SingleSale)

    @pytest.mark.parametrize(
        "text",
        [
            "1x gold case ($10) (Cash) Sell",     # old parenthesised-method habit
            "1x gold case ($10 Cash Sell",        # mismatched bracket
            "2x pack ($1,000) PayNow Sell",       # comma amount
        ],
    )
    def test_sale_shaped_failures_quarantine(self, text):
        result = parse_message(text)
        assert isinstance(result, Quarantine)
        assert result.raw_text == text

    def test_trade_parses(self):
        assert isinstance(parse_message("Trade PSA9 Zard for PSA10 Pika +$50 Cash"), Trade)

    def test_cart_parses(self):
        assert isinstance(parse_message("2x pack ($20)\n1x case ($10)\n$30 PayNow"), MixedCart)

    @pytest.mark.parametrize(
        "text",
        [
            "anyone bringing extra sleeves tomorrow?",
            "booth setup at 9am",
            "the 10x lens photos look great",   # 10x but no ($ price
            "lunch was $12 lol",                # $ but no method
        ],
    )
    def test_ordinary_chat_ignored(self, text):
        assert parse_message(text) is None


class TestTrailingNotes:
    """2026-07-19: trailing free text after the keywords -> Notes column
    (consignment: '1x Sam mew rc $15 cash' became '1x mew rc $15 cash Sam')."""

    def test_note_after_method(self):
        sale = parse_single_sale("1x mew rc $15 cash Sam")
        assert sale.line.item == "mew Raw card"
        assert sale.method is Method.CASH
        assert sale.sale_type is SaleType.SELL
        assert sale.note == "Sam"

    def test_note_straight_after_price(self):
        sale = parse_single_sale("2x p $20 Sam")
        assert sale.line.item == "Booster pack"
        assert sale.method is Method.PAYNOW
        assert sale.note == "Sam"

    def test_multi_word_note_after_buyback(self):
        sale = parse_single_sale("1x zard psa9 $80 buyback ah beng consignment")
        assert sale.sale_type is SaleType.BUYBACK
        assert sale.note == "ah beng consignment"

    def test_no_note_stays_empty(self):
        assert parse_single_sale("2x p $20").note == ""
        assert parse_single_sale("1x mew $120 cash sell").note == ""

    def test_cart_note_on_total_line(self):
        cart = parse_mixed_cart("2x p $20\n1x etb $55\n$75 cash Sam")
        assert cart.method is Method.CASH
        assert cart.note == "Sam"

    def test_cart_total_without_note_unchanged(self):
        assert parse_mixed_cart("2x pack $20\n1x case $10\n$30").note == ""

    def test_keyword_after_note_quarantines(self):
        # "cash" typed after the note: the method would silently default wrong
        result = parse_message("2x p $20 Sam cash")
        assert isinstance(result, Quarantine)
        assert "must come before the note" in result.reason

    @pytest.mark.parametrize("text,keyword", [
        ("1x zard psa9 $80 buybak", "buyback"),     # would log as a Sell!
        ("1x mew $15 chash", "cash"),               # would log as PayNow!
        ("2x p $20 selll", "sell"),
    ])
    def test_one_typo_keyword_quarantines(self, text, keyword):
        result = parse_message(text)
        assert isinstance(result, Quarantine)
        assert keyword in result.reason

    def test_money_in_note_quarantines(self):
        result = parse_message("1x mew $15 Sam $20")
        assert isinstance(result, Quarantine)
        assert "$" in result.reason

    def test_note_does_not_span_lines(self):
        # a second message line is NOT a note; sale-shaped mess still quarantines
        assert isinstance(parse_message("2x p $20\nClaimed"), Quarantine)

    def test_note_never_expands_abbreviations(self):
        assert parse_single_sale("1x mew $15 rc").note == "rc"  # note kept as typed

    def test_plain_trailing_text_is_now_a_note(self):
        # pre-notes grammar rejected trailing text; it is the feature now
        sale = parse_message("1x gold case ($10) Cash Sell extra")
        assert isinstance(sale, SingleSale)
        assert sale.note == "extra"

    @pytest.mark.parametrize("text", [
        "1x gold case ($10) (Cash) Sell",   # parenthesised method (old habit)
        "1x gold case ($10) Card Sell",     # unknown method absorbs the type
    ])
    def test_keyword_hidden_in_note_quarantines(self, text):
        # these used to be plain rejections; the note grammar would swallow
        # them silently, so the keyword guard turns them into quarantines
        result = parse_message(text)
        assert isinstance(result, Quarantine)
        assert "must come before the note" in result.reason
