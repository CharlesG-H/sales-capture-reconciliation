# PRD — Tradeshow Sales Tracking Automation

> Snapshot of the Confluence source of truth (last modified 2026-07-09).
> If this file and Confluence disagree, Confluence wins.

**Initiative:** tradeshow-sales-automation
**Date:** 2026-07-09
**Owner:** Charles (product owner / vendor)
**Team:** trading-card vending team (~11 members)
**Status:** Draft for build hand-off

---

## 1. Executive Summary

Sales at the team's tradeshow booth are currently captured as photos posted into a per-show Telegram topic, then manually consolidated into a Google Sheet at the end of each day. That manual consolidation is where records break — mistypes, double-counts, and skipped entries produce loose-pack drift ("missing packs") that forces the team to backtrack.

This initiative builds a Telegram bot that reads fixed-format sale captions from each show's topic and writes structured rows to the Google Sheet automatically, eliminating manual keying. Anything it cannot cleanly parse is quarantined for review rather than written in wrong. Delivery is phase one of two; a live-inventory system is phase two.

**Top success metric:** zero manual data-entry rows — every sale reaches the sheet without anyone keying it — with daily money totals that reconcile against payment screenshots.

## 2. Problem Statement

**Current state.** Every sale is photographed with the payment screenshot (or cash) placed beside the item, then posted to a per-show Telegram topic. Sellers already caption these posts in a rough structured style (e.g. "1x gold case ($10) (Cash)"). One person then manually transcribes the topic into a Google Sheet after the show.

**Who is affected.** The ~11-person vending team, and specifically whoever owns end-of-day consolidation.

**Severity.** The transcription step silently corrupts the record. The recurring, named symptom is loose packs going "missing" — the count doesn't reconcile, and the team spends time reconstructing whether items sold. Because capture is reliable (photos are never missed), the defect is isolated to consolidation.

**Evidence.** Qualitative owner report of recurring missing packs and backtracking; live Telegram screenshots confirming the existing caption habit. *No quantitative baseline (error rate, packs lost per show, consolidation time) exists — flagged as a gap.*

## 3. Background & Context

The team vends graded slabs (PSA cert numbers on the label), sealed product (product name printed on the box), and loose packs (fungible, high-frequency, low-value). Each show already gets its own Telegram topic, giving natural per-show isolation, and the permanent topic history means the sheet can always be rebuilt from Telegram if needed — the topic is the source of truth, the sheet is derived.

The owner has explicitly chosen a two-phase approach: automate capture-to-sheet first (this PRD), then build a live-inventory system second. A key design principle carried throughout: for a system whose purpose is accurate records, a **caught gap beats a silent error** — the bot flags rather than guesses.

## 4. Goals & Success Metrics

**Business goals:** remove manual end-of-day data entry; make the sales record trustworthy; lay a clean structured-data foundation for the phase-two inventory system.

| KPI | Definition | Target |
| --- | --- | --- |
| Manual keying eliminated | Rows reaching the sheet without human entry | 100% of parseable sales |
| Money reconciliation | Daily cash + PayNow totals tie to payment evidence | Ties out each show |
| Loose-pack drift | "Missing packs" requiring backtracking | Reduced vs today *(baseline TBD)* |
| Quarantine rate | Share of captions the bot can't parse | Low enough to review by hand end-of-day *(threshold TBD)* |

**Guardrails:** the bot never rounds or "cleans" a parsed figure — it stores exactly what was typed; the bot never writes a row it isn't confident it parsed correctly (quarantine instead).

*Targets marked TBD were not quantified in discussion; capturing a baseline at the next show is recommended (see Open Questions).*

## 5. Scope

**In scope**

* Telegram bot reading one designated topic per show and writing to the show's Google Sheet tab.
* Three caption shapes: Sell, Buyback, and Trade (see Functional Requirements).
* Mixed carts grouped by **single message** (one message = one payment).
* Quantity captured on every sale line.
* Exact total-paid stored to the cent, unrounded.
* Parse-or-quarantine handling with a real-time reply on failure.
* Re-reading edited messages and handling deletions.
* A source-photo link stored on every row.
* Seller identity captured per row.
* Daily totals broken out by payment method (cash vs PayNow).

**Out of scope (Future Considerations / Phase Two)**

* Live stock counts and opening/closing reconciliation (the full inventory system).
* Standardised / canonical item names and sum-by-product reporting.
* Consignment attribution ("AG" / supplier settlement).
* OCR of the photo contents (captions are the record; photos are evidence only).

## 6. Functional Requirements

Priorities: **P0** = required for a usable first version · **P1** = important, soon after · **P2** = nice-to-have.

| ID | Requirement | Priority | Acceptance Criteria |
| --- | --- | --- | --- |
| FR-1 | Parse the **Sell/Buyback** caption `[qty]x [item] ($[total]) [Cash/PayNow] [Sell/Buyback]` | P0 | A conforming caption produces one sheet row with qty, free-text item, exact total (to the cent), method, and type correctly populated. `Buyback` records cash-out / stock-in (opposite sign to `Sell`). |
| FR-2 | Store the money field as the **exact total paid, unrounded** | P0 | `$113.30` is stored as `113.30`, never rounded. Unit price, if shown, is derived, not stored. No parsed figure is altered. |
| FR-3 | Capture **quantity** on every sale line | P0 | Every sell/buyback row has an integer quantity. |
| FR-4 | Parse the **Trade** caption `Trade [gave] for [got] ±$[cash] [Cash/PayNow]` | P0 | Produces a trade row with gave-item, got-item, and a signed cash figure (`+` = cash in, `-` = cash out, blank = 0 / even swap). |
| FR-5 | **Mixed cart grouping by single message** | P0 | Multiple sale lines in one Telegram message are treated as one payment. The bot sums their totals and verifies the sum ties to the payment shown; a mismatch is flagged, not written as-is. |
| FR-6 | **One sale posted as one message with its evidence** | P0 | The caption and its payment screenshot (or cash photo) are in the same message so the row can link to the correct image. |
| FR-7 | **Parse-or-quarantine** | P0 | Any caption that does not cleanly match a known shape is placed in a "needs review" state and is NOT written as a confident row. |
| FR-8 | **Real-time reply on parse failure** | P1 | When a caption fails to parse, the bot replies in-thread with the expected format so it can be fixed at the table. |
| FR-9 | **Re-read edits** | P0 | Editing a sale message updates the corresponding row; the prior value is retained in an audit field. |
| FR-10 | **Handle deletions** | P1 | A deleted sale message marks its row void (not erased). A periodic re-scan catches deletions Telegram does not notify. |
| FR-11 | **Store source-photo link per row** | P0 | Every row carries a pointer (message ID / permalink) to its source message for later reconciliation. |
| FR-12 | **Capture seller identity** | P1 | Each row records which team member posted it. |
| FR-13 | **Noise filter** | P1 | Ordinary chat (non-sale messages) is ignored; only sale-shaped messages are parsed or quarantined. |
| FR-14 | **Daily totals by payment method** | P1 | At end of show, the bot/sheet produces cash-in, PayNow-in, and cash-out (buyback) totals to reconcile against the till. |
| FR-15 | **Per-show sheet tab** | P0 | Each show's sales land in their own sheet tab, mirroring the per-topic isolation. |

## 7. Dependencies

**Technical**

* Telegram Bot API access; a runtime/host to keep the bot running during shows (with venue connectivity).
* Google Sheets API access and write credentials to the target sheet.

**Configuration (critical)**

* The bot must have **privacy mode OFF** (or be a group admin) or it cannot read ordinary group messages — without this it reads nothing.
* Confirm the current setup is **topics within one group** (not a new group per show), so the bot is added once rather than re-invited each show.

**Process / human**

* Sellers post sales as one message containing caption + evidence, following the fixed caption formats.

## 8. Risks & Mitigation

| Risk | Probability | Impact | Mitigation | Contingency |
| --- | --- | --- | --- | --- |
| Sellers deviate from the fixed caption format | Medium | Medium | Real-time parse-failure reply (FR-8); short reference card; quarantine catches misses | High quarantine volume reviewed manually end-of-day until format habit sets in |
| Telegram doesn't reliably notify the bot of deletions | Medium | Medium | Periodic re-scan of the topic (FR-10) | Manual void via a correction message |
| Typed amount ≠ amount actually paid (caption/screenshot mismatch) | Medium | Medium | Photo link on every row (FR-11); daily total tie-out surfaces gross errors | End-of-day reconciliation against screenshots |
| All-in **bundle** price with no per-item split | Medium | Low | Split across lines manually, or log as a single bundle line — total still ties to screenshot | See Open Questions (OQ-1) |
| Cash sales have no transaction reference number | Medium | Low | Rely on message/photo identity for de-duplication rather than a payment ref | Manual review of cash rows |
| Free-text item names prevent sum-by-product reporting | High | Low (accepted) | Deferred to phase two by design | Standardisation handled with the inventory system |
| Venue connectivity drops mid-show | Low | Medium | Topic history is the source of truth; sheet is rebuildable | Bot re-processes the topic once back online |

## 9. Open Questions

| ID | Question | Owner | Target decision |
| --- | --- | --- | --- |
| OQ-1 | For a true all-in **bundle** price with no per-item prices: split across lines manually, or log as one bundle line? (Working default: split yourself; total still ties to the screenshot.) | Charles | Before build of FR-5 |
| OQ-2 | Capture a **quantitative baseline** at the next show (packs lost, consolidation time, sales volume) so success metrics have real targets? | Charles | Next show |
| OQ-3 | Confirm the acceptable **quarantine-rate threshold** and who reviews quarantined items end-of-day | Charles | Before launch |
| OQ-4 | Confirm current Telegram structure is **topics-in-one-group** and set bot privacy mode / admin accordingly | Charles + builder | Before build |
| OQ-5 | De-duplication rule for **cash** sales (no reference number) if a message is reposted | Builder | During FR-7 build |

---

*Resolved during discovery: mixed carts are grouped by single message (no `#tag`); money is stored to the cent unrounded; buybacks ride the sell template with a flipped type; trades use a dedicated one-line shape; captions are the record and photos are evidence.*

---

## Appendix A — Decisions locked at build kick-off (2026-07-15)

Recorded from the build-planning session with Charles; these resolve the open questions that gated the design.

| Ref | Decision |
| --- | --- |
| OQ-4 | One group with topics confirmed. Bot will be added as a **group admin**. Per-show routing keys off `message_thread_id`. |
| OQ-1 | Bundles are **split manually by the seller** into priced lines — no bundle grammar. |
| OQ-3 | Quarantine lands in a dedicated **"Needs Review" sheet tab**, reviewed end-of-day. |
| OQ-5 | **Telegram message ID = row identity.** Repost = new row; delete voids the old one. Processing is idempotent by message ID. |
| FR-5 format | Mixed cart = sale lines **without** method, then a typed total line, e.g. `2x Evolving Skies pack ($20)` / `1x gold case ($10)` / `$30 PayNow`. The bot verifies the line sum equals the typed total exactly; mismatch → quarantine. Cart lines are implicitly Sell; buybacks and trades are always single messages. |
| FR-10 constraint | The Telegram **Bot API cannot read message history or receive delete events**, so the PRD's "periodic re-scan" is not possible with a bot token alone. v1 mitigation: admin `/void` command. MTProto user-session re-scan is a P1 decision. |

---

## As-built caption templates (v1 — locked 2026-07-18)

Locked by Charles as the default for all trade shows. Team-facing version in
`docs/reference-card.md`; Confluence PRD page 7274499 updated to match (v2).

Defaults: **PayNow and Sell are assumed** — sellers only type what's
different. Case-insensitive; price brackets optional; $ = line TOTAL.

| Shape | Example |
| --- | --- |
| Sell (minimal) | `2x p $20` |
| Cash sale | `1x mew rc $15 cash` (method accepted before or after sale type) |
| Buyback | `1x zard psa9 $80 buyback [cash]` |
| Trade | `Trade PSA9 Zard for PSA10 Pika +$50` (+ they pay, - we pay; sign required; omit for even) |
| Mixed cart | priced lines + final total line `$75`; must tie exactly; writes ONE row |
| Owner / note | trailing free text after the keywords → Notes column: `1x mew rc $15 cash Sam`; carts take it on the total line |

Short forms (word-level, any casing, work after any set name):
BB = Booster bundle, P = Booster pack, ETB = Elite Trainer box,
UPC = Ultra premium collection, RC = Raw card, SB = Shrinked box,
UB = Unshrinked box.

Spec amendments decided during build (2026-07-17/18/19):

- Trailing notes (2026-07-19, consignment use case): free text after the
  price/keywords on the sale or cart-total line lands in Notes, as typed.
  Guards quarantine a note that contains a `$` amount, a keyword after free
  text (`$20 Sam cash`), or a word one typo from a keyword (`buybak`) —
  those are more likely mistyped sales than notes. Notes never span lines;
  trades take no trailing note in v1; edits do not rewrite Notes.

- Sell + PayNow grammar defaults; two conflicting methods quarantine.
- Mixed cart = one row (itemization in Item name, Qty = total pieces, Amount = payment).
- Sheet template is 10 columns: Sold date, Item name, Qty, Amount ($), Payment,
  Sale Type, Trade, Notes, Msg ID, Link. Status/Audit/Cart Total/Seller removed;
  FR-12 dropped (the Link identifies the poster).
- FR-9 as built: edits update the row in place (Msg ID key, Notes preserved);
  unparseable edits leave the row and flag Needs Review.
- FR-10 as built: manual `/void <Msg ID>` marks Notes MESSAGE DELETED; row kept.
- Bot is opt-in per topic (`/track` / `/untrack`); tabs auto-created per topic
  title, styled as Sheets tables with self-deleting placeholder rows.
- OQ-1 resolved: bundles log as a single line/row.

---

## Hosting (as-built 2026-07-19)

The "runtime/host to keep the bot running during shows" dependency (Section 7)
is resolved: the bot is deployed to **Google Cloud Run** in webhook mode.

- Telegram pushes each message to the service over HTTPS (secret-token
  verified); the service scales to zero between messages, so hosting stays
  well within the free tier at team volume.
- One `/track` in a topic covers the whole show — tracking is persistent
  state, not a bot start. State lives in the spreadsheet's hidden "Bot State"
  tab, so it survives redeploys and instance recycling.
- Cloud credentials: the service runs as the existing Google service account
  (ambient credentials); no key file or `.env` is ever uploaded.
- Local long polling remains the development/fallback mode (requires
  deleting the Telegram webhook first — exactly one listener at a time).
- Single region, max 1 instance (protects the single-writer assumption on the
  sheet).
- Operational note: the GCP trial must be "activated" (a button, not a
  payment) before it expires or the service pauses.
