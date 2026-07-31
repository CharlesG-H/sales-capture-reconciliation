# Sales caption reference card

Locked as the default template for all trade shows — 2026-07-17 (amended
2026-07-18: Sell default, short forms; 2026-07-19: trailing notes). Pin the
message in the "Telegram pin version" section below in an UNTRACKED topic or
General — inside a tracked topic its sale-shaped example lines would land in
Needs Review.

## Telegram pin version (copy-paste)

```
📋 LOGGING SALES — CHEAT SHEET

One message per sale, in this topic.
Attach the payment screenshot / cash photo to the SAME message.
PayNow + Sell are assumed — only type what's different.

✅ SELL
2x p $20
1x abyss eye sb $60

💵 CASH SALE — add "cash"
1x mew rc $15 cash

🔄 BUYBACK — we pay the customer
1x zard psa9 $80 buyback
1x zard psa9 $80 buyback cash

🤝 TRADE — +$ they pay us, -$ we pay them
Trade PSA9 Zard for PSA10 Pika +$50
Trade slab A for slab B

🛒 MULTIPLE ITEMS, ONE PAYMENT
One line per item, last line = total paid (must add up exactly):
2x p $20
1x etb $55
$75

📝 OWNER / NOTE — always LAST on the line
1x mew rc $15 cash Sam        <- "Sam" goes to the Notes column
2x p $20 Sam
For multiple items: put the name on the total line ($75 cash Sam)

🔤 SHORT FORMS (any casing)
BB = Booster bundle
P = Booster pack
ETB = Elite Trainer box
UPC = Ultra premium collection
RC = Raw card
SB = Shrinked box
UB = Unshrinked box

⚠️ REMEMBER
• $ = TOTAL for the line, not per piece
• Max 2 decimals, no commas ($1000 not $1,000)
• Owner name / note comes LAST — after price and cash/sell/buyback
• Typo? Just EDIT your message — the sheet fixes itself
• Deleted a message? Post: /void followed by the Msg ID from the sheet
• If the bot can't read it, it goes to "Needs Review" — copy an example above if unsure
```

## Formats

**Sale** — Sell and PayNow are assumed; the minimal caption is qty + item + price.
Add `Cash` for cash (before or after Sell both work); brackets around price optional.

```
2x p $20                               <- shortest form: PayNow Sell
1x Mew ex SIR $120 Cash
1x Mew ex SIR $120 Cash Sell
3x Evolving Skies pack $9.60 Sell      <- $ amount = TOTAL for the line
```

**Buyback** (we pay the customer)

```
1x Charizard PSA 9 $80 Buyback
1x Charizard PSA 9 $80 Cash Buyback
```

**Trade** (`+` = customer pays us, `-` = we pay; sign required whenever money moves)

```
Trade PSA9 Zard for PSA10 Pika +$50
Trade PSA10 Pika for PSA9 Zard -$30 Cash
Trade slab A for slab B                <- even trade, no money part
```

**Multiple different items, one payment** (last line = what was paid; must
equal the sum of the item lines exactly, or the message quarantines)

```
2x pack $20
1x case $10
$30                                    <- or "$30 Cash"
```

**Owner / note** — anything typed after the price and keywords (same line)
lands in the sheet's Notes column, e.g. for a friend's consigned card:

```
1x mew rc $15 cash Sam                <- Notes: "Sam"
2x p $20 Sam                          <- works straight after the price too
$75 cash Sam                          <- carts: note on the total line
```

The note must come LAST: `2x p $20 Sam cash` quarantines (the bot refuses
to guess whether that cash was meant as the payment). Typos that look like
keywords (`buybak`, `chash`) also quarantine rather than logging wrong.

Each message above = exactly one sheet row.

## Item short forms

These expand automatically (any casing) — the sheet shows the full name:

| You type | Sheet shows |
| --- | --- |
| `BB` | Booster bundle |
| `P` | Booster pack |
| `ETB` | Elite Trainer box |
| `UPC` | Ultra premium collection |
| `RC` | Raw card |
| `SB` | Shrinked box |
| `UB` | Unshrinked box |

Codes follow any set name: `1x abyss eye SB $60` logs as "abyss eye Shrinked box".

Works inside names too: `2x AH BB $220 Sell` logs as "AH Booster bundle".

## Rules

- Start item lines with the quantity: `1x`, `2x`, ...
- The `$` amount is the total for that line, max 2 decimals, no commas.
- Owner names / notes go last on the line, after the keywords; they are
  stored in Notes exactly as typed (short forms are NOT expanded there).
  A note can't span lines and can't contain a `$` amount.
- Casing never matters; keywords are stored canonical (`PayNow`, `Cash`, `Sell`, `Buyback`, `Trade`).
- One sale = one message, with the payment screenshot / cash photo attached
  to the same message.
- Made a mistake? Just edit the message — the sheet row updates itself.
  (If your edit breaks the format, the row stays as it was and the edit
  lands in Needs Review.)
- No extra words in the caption (no "Claimed" prefix etc.).
- The bot only reads topics where `/track` was posted; `/untrack` turns it off.
- Deleted a sale message? Telegram doesn't tell bots about deletions — post
  `/void <Msg ID>` in the topic (Msg ID is in the sheet row). The row is kept
  and its Notes cell is marked MESSAGE DELETED.
- Unreadable sale-shaped messages land in the "Needs Review" tab, never the show tab.
