# Sales Capture & Reconciliation

A Telegram → Google Sheets pipeline that turns free-text booth sales into a
clean, reconcilable record. Sellers type a short caption at the table; the bot parses
it and writes a structured row. **Anything it can't parse cleanly goes to a
"Needs Review" tab — it never writes a guessed row.**

Built solo, end to end: discovery, PRD, caption grammar, parser, test suite,
and deployment to Google Cloud Run.

- Spec: [`docs/prd.md`](docs/prd.md)
- Team-facing cheat sheet: [`docs/reference-card.md`](docs/reference-card.md)

## The problem

A ~11-person trading-card vending team captures every booth sale the same way:
photograph the item beside the payment screenshot, post it into the show's
Telegram topic with a rough caption. **Capture is bulletproof — nobody misses a
photo.** The record breaks afterwards, when one person manually retypes the
whole topic into a spreadsheet at the end of the day. Mistypes, double-counts
and skipped entries produce the team's recurring symptom: packs going
"missing", counts that don't reconcile, and evenings spent reconstructing
whether an item actually sold.

Because capture was already reliable, the defect was isolated to a single
step: manual consolidation. That's the step this automates.

## Design principle

> For a system whose whole purpose is an accurate record, a caught gap beats a
> silent error.

The bot never rounds, never "cleans" a parsed figure, and never writes a row it
isn't confident in. Money is stored exactly as typed, to the cent. Everything
ambiguous is quarantined for end-of-day triage instead of being written wrong.

## Caption grammar

Sellers type one-handed at a busy table, so every keystroke has to earn its
place. **Sell and PayNow are assumed defaults**, so the minimal sale is three
tokens. Case-insensitive; price brackets optional; `$` is the line total.

```
# Sell (minimal) / cash / buyback
2x p $20
1x mew rc $15 cash
1x zard psa9 $80 buyback

# Mixed cart — lines plus a typed total (one message = one row = one payment)
2x p $20
1x etb $55
$75

# Trade (± cash: + they pay us, - we pay, omit if even swap)
Trade PSA9 Zard for PSA10 Pika +$50

# Trailing free text becomes the Notes cell (e.g. a consignor's name)
1x mew rc $15 cash Sam
```

Word-level short forms expand to full product names in the sheet
(`p` → Booster pack, `etb` → Elite Trainer box, `bb`, `upc`, `rc`, `sb`, `ub`).

### Where the grammar refuses to guess

- **Mixed carts must tie out.** Line items are summed and compared against the
  typed total. A mismatch quarantines rather than writing either figure.
- **Two payment methods in one caption** is ambiguous, so it fails the parse.
- **Notes are guarded.** A "note" containing a `$` amount, a real keyword, or a
  word one edit away from a keyword (`buybak`) is more likely a mistyped sale
  than a note, so it quarantines. This is a Levenshtein-distance-1 check used
  only as a guard — it never auto-corrects anything.
- **Sale-shaped but unparseable** text quarantines with the expected formats;
  ordinary chat is ignored entirely.

## Architecture

```
Telegram topic ──webhook──> Cloud Run service ──> parser ──> Google Sheets
                                                     │
                                                     └──> "Needs Review" tab
```

- **Idempotent by message ID.** The Telegram message ID is the row's identity,
  so reprocessing is safe: an edit updates its row, a repost is a new row, and
  a delete is voided rather than erased.
- **Deletes can't be detected**, so they're handled by an admin `/void`
  command. The Telegram Bot API can't read history or receive delete events,
  which killed the periodic re-scan the PRD originally called for. See
  [Spec vs reality](#spec-vs-reality).
- **Tracking is opt-in per show** via `/track` in a topic, with sheet tabs
  created automatically per show. `/untrack` stops it.
- **Webhook or polling.** With `WEBHOOK_URL` set the bot serves a webhook and
  scales to zero between messages; unset, it falls back to local long polling.
  Exactly one listener can exist at a time.
- **Capped at one instance**, which protects the single-writer assumption on
  the spreadsheet.
- **State survives redeploys.** In the cloud, tracked-topic state lives in a
  hidden "Bot State" tab, because Cloud Run has no durable disk.
- **No key file in the cloud.** The service runs as a service account using
  ambient credentials; `.gcloudignore` blocks `.env` and keys from uploads.

Sale rows carry: `Sold date · Item name · Qty · Amount ($) · Payment ·
Sale Type · Trade · Notes · Msg ID · Link`. Review rows carry the raw text and
the reason it was held back.

## Spec vs reality

Two places where the PRD had to bend once it met the platform, both documented
rather than quietly dropped:

1. **Periodic re-scan → `/void`.** The spec assumed the bot could re-read a
   topic to catch deletions. The Bot API can't, so deletion became an explicit
   admin command and message ID became the row identity.
2. **Seller identity capture → cut.** The message link already identifies the
   poster, so a dedicated field was redundant. The sheet slimmed to 10 columns.

## Setup

1. **Telegram bot** — talk to [@BotFather](https://t.me/BotFather): `/newbot`,
   copy the token. Add the bot to your group and promote it to **admin** so it
   can read topic messages.
2. **Google service account** — in the Google Cloud Console: create a project,
   enable the *Google Sheets API*, create a service account and a JSON key,
   save it in this folder as `service-account.json` (gitignored). Share your
   spreadsheet with the service account's email as **Editor**.
3. **Configure** — copy `.env.example` to `.env` and fill in your values.
   `.env`, service-account keys and the webhook secret are all gitignored and
   must never be committed.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python scripts/check_setup.py   # verifies credentials, finds your chat ID
.venv/bin/python -m pytest                # parser test suite
.venv/bin/python -m bot.main              # run (long polling)
```

Deploying to Cloud Run is a single `gcloud run deploy --source .` against your
own project; run it with `--max-instances 1` to preserve the single-writer
guarantee.

## Status

v1 is live on Cloud Run. The success metric — zero manually keyed rows, with
daily cash and PayNow totals that tie out to payment evidence — is measured at
the first full show under the bot. The structured rows are also the deliberate
foundation for phase two, a live-inventory system that only works if the data
underneath it is trustworthy.
