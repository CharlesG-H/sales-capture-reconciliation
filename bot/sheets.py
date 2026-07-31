"""Google Sheets writer. All writes use RAW input so money strings land in
cells exactly as typed (FR-2) — Sheets never reinterprets or reformats them."""

import logging
from pathlib import Path

import google.auth
import gspread

log = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Table look copied from the user's Sheet3 "Inventory tracker" template:
# slate header, white/pale-grey banded rows. Money/date columns carry no
# columnType on purpose — CURRENCY/DATE would validate or coerce the exact
# typed strings (FR-2); only fixed-vocabulary columns get dropdown chips.
_TABLE_ROWS_PROPERTIES = {
    "headerColorStyle": {"rgbColor": {"red": 0.384, "green": 0.431, "blue": 0.478}},
    "firstBandColorStyle": {"rgbColor": {"red": 1, "green": 1, "blue": 1}},
    "secondBandColorStyle": {"rgbColor": {"red": 0.965, "green": 0.973, "blue": 0.976}},
}

_HEADER_FORMAT = {  # white bold text against the slate header band
    "textFormat": {
        "bold": True,
        "foregroundColorStyle": {"rgbColor": {"red": 1, "green": 1, "blue": 1}},
    }
}


def _dropdown(index: int, name: str, *options: str) -> dict:
    return {
        "columnIndex": index,
        "columnName": name,
        "columnType": "DROPDOWN",
        "dataValidationRule": {
            "condition": {
                "type": "ONE_OF_LIST",
                "values": [{"userEnteredValue": o} for o in options],
            }
        },
    }


# Dropdown chips for the sale-tab columns with fixed vocabularies. The bot
# always writes these exact strings, so no row ever flags invalid.
_SALE_TABLE_COLUMNS = [
    _dropdown(4, "Payment", "PayNow", "Cash"),
    _dropdown(5, "Sale Type", "Sell", "Buyback", "Trade"),
]

# Sale data first, bot bookkeeping at the right (audited 2026-07-17):
# Amount is the money exactly as typed (signed for trades); Cart Total ties
# multi-item rows to their one payment; Notes is hand-filled; Msg ID is the
# row-identity key.
SALE_HEADERS = [
    "Sold date", "Item name", "Qty", "Amount ($)", "Payment",
    "Sale Type", "Trade", "Notes",
    "Msg ID", "Link",
]
# Placeholder rows stamped into each new sale tab (like the Sheet3 template's
# sample rows): identical generic rows, grey-italic, marked EXAMPLE in Notes
# so they are never mistaken for real sales. Delete them once real rows land.
_EXAMPLE_ROW = [
    "2026-07-26 14:05:00", "Item name", "1", "120",
    "PayNow", "Sell", "PSA9 Zard -> PSA10 Pika", "EXAMPLE — delete me", "", "",
]
SALE_EXAMPLE_ROWS = [_EXAMPLE_ROW] * 5

_EXAMPLE_ROW_FORMAT = {  # grey italic so placeholders read as placeholders
    "textFormat": {
        "italic": True,
        "foregroundColorStyle": {"rgbColor": {"red": 0.55, "green": 0.55, "blue": 0.55}},
    }
}

REVIEW_HEADERS = ["Timestamp", "Topic", "Link", "Raw text", "Reason", "Resolved"]

REVIEW_TAB = "Needs Review"


class SheetsClient:
    def __init__(self, key_file: Path | None, spreadsheet_id: str):
        if key_file is not None:
            client = gspread.service_account(filename=key_file)
        else:
            # No key file (Cloud Run): the service runs AS the service account,
            # so ambient credentials replace the JSON key entirely.
            credentials, _ = google.auth.default(scopes=_SCOPES)
            client = gspread.authorize(credentials)
        self._spreadsheet = client.open_by_key(spreadsheet_id)
        self._example_free: set[str] = set()  # tabs known to have no EXAMPLE rows

    def _ensure_tab(
        self,
        title: str,
        headers: list[str],
        table_columns: list[dict] | None = None,
        example_rows: list[list[str]] | None = None,
        as_table: bool = True,
    ) -> gspread.Worksheet:
        try:
            return self._spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            ws = self._spreadsheet.add_worksheet(title, rows=1000, cols=len(headers))
            self._write_rows(ws, [headers])
            if as_table:
                ws.format("1:1", _HEADER_FORMAT)
                self._make_table(ws, len(headers), table_columns)
            if example_rows:
                self._write_rows(ws, example_rows)
                ws.format(f"2:{1 + len(example_rows)}", _EXAMPLE_ROW_FORMAT)
            return ws

    @staticmethod
    def _write_rows(ws: gspread.Worksheet, rows: list[list[str]]) -> None:
        """Write at the first row with no data. The Sheets append API is not
        usable here: it appends BELOW the pre-built table's 1000-row range,
        burying entries under the empty banded rows."""
        next_row = len(ws.col_values(1)) + 1
        ws.update(values=rows, range_name=f"A{next_row}", raw=True)

    def _make_table(
        self, ws: gspread.Worksheet, num_cols: int, table_columns: list[dict] | None
    ) -> None:
        """Convert the tab to a pre-built Sheets table (banding, filter chips,
        dropdowns). Purely cosmetic — a failure here must never cost a sale row."""
        table = {
            "name": f"Table_{ws.id}",  # table names must be spreadsheet-unique
            "range": {
                "sheetId": ws.id,
                "startRowIndex": 0, "endRowIndex": ws.row_count,
                "startColumnIndex": 0, "endColumnIndex": num_cols,
            },
            "rowsProperties": _TABLE_ROWS_PROPERTIES,
        }
        if table_columns:
            table["columnProperties"] = table_columns
        try:
            self._spreadsheet.batch_update({"requests": [{"addTable": {"table": table}}]})
        except gspread.exceptions.APIError:
            log.warning("could not convert tab %r to a table; leaving plain", ws.title)

    def append_sale_rows(self, tab: str, rows: list[list[str]]) -> None:
        ws = self._ensure_tab(tab, SALE_HEADERS, _SALE_TABLE_COLUMNS, SALE_EXAMPLE_ROWS)
        self._drop_example_rows(ws)
        self._write_rows(ws, rows)

    _MSG_ID_COL = SALE_HEADERS.index("Msg ID") + 1
    _NOTES_COL = SALE_HEADERS.index("Notes")

    def has_sale_row(self, tab: str, msg_id: int) -> bool:
        ws = self._ensure_tab(tab, SALE_HEADERS, _SALE_TABLE_COLUMNS, SALE_EXAMPLE_ROWS)
        return ws.find(str(msg_id), in_column=self._MSG_ID_COL) is not None

    def update_sale_row(self, tab: str, msg_id: int, row: list[str]) -> bool:
        """FR-9: overwrite the row keyed by Msg ID with re-parsed values.
        The hand-filled Notes cell is left untouched. False if no row exists."""
        ws = self._ensure_tab(tab, SALE_HEADERS, _SALE_TABLE_COLUMNS, SALE_EXAMPLE_ROWS)
        cell = ws.find(str(msg_id), in_column=self._MSG_ID_COL)
        if cell is None:
            return False
        before_notes = row[: self._NOTES_COL]
        after_notes = row[self._NOTES_COL + 1 :]
        ws.batch_update(
            [
                {"range": f"A{cell.row}:G{cell.row}", "values": [before_notes]},
                {"range": f"I{cell.row}:J{cell.row}", "values": [after_notes]},
            ],
            value_input_option="RAW",
        )
        return True

    def _drop_example_rows(self, ws: gspread.Worksheet) -> None:
        """The first real entry replaces the placeholders: delete EXAMPLE rows
        so live data starts at the top of the table."""
        if ws.title in self._example_free:
            return
        head = ws.get_values(f"A2:J{2 + len(SALE_EXAMPLE_ROWS) + 4}")
        example_rows = [
            i + 2 for i, row in enumerate(head) if any("EXAMPLE" in cell for cell in row)
        ]
        for row_index in reversed(example_rows):  # bottom-up so indices stay valid
            ws.delete_rows(row_index)
        self._example_free.add(ws.title)

    def ensure_sale_tab(self, tab: str) -> None:
        self._ensure_tab(tab, SALE_HEADERS, _SALE_TABLE_COLUMNS, SALE_EXAMPLE_ROWS)

    def rename_sale_tab(self, old: str, new: str) -> None:
        try:
            self._spreadsheet.worksheet(old).update_title(new)
        except gspread.WorksheetNotFound:
            self._ensure_tab(new, SALE_HEADERS, _SALE_TABLE_COLUMNS, SALE_EXAMPLE_ROWS)

    def mark_deleted(self, tab: str, msg_id: int) -> bool:
        """FR-10 (/void): the row stays; Notes records that its source message
        was deleted. False if no row carries this Msg ID."""
        ws = self._ensure_tab(tab, SALE_HEADERS, _SALE_TABLE_COLUMNS, SALE_EXAMPLE_ROWS)
        cell = ws.find(str(msg_id), in_column=self._MSG_ID_COL)
        if cell is None:
            return False
        notes_cell = f"{chr(ord('A') + self._NOTES_COL)}{cell.row}"
        existing = ws.acell(notes_cell).value or ""
        note = "MESSAGE DELETED" + (f" — {existing}" if existing else "")
        ws.update(range_name=notes_cell, values=[[note]], raw=True)
        return True

    def append_review_row(self, row: list[str]) -> None:
        ws = self._ensure_tab(REVIEW_TAB, REVIEW_HEADERS)
        self._write_rows(ws, [row])


STATE_TAB = "Bot State"
STATE_HEADERS = ["Topic ID", "Name", "Tracked"]


class SheetTopicStore:
    """Topic state persisted in a hidden tab of the spreadsheet itself, so it
    survives Cloud Run's disposable filesystem. One row per topic:
    Topic ID | Name | Tracked ("yes" / blank)."""

    def __init__(self, sheets: SheetsClient):
        self._sheets = sheets

    def _worksheet(self) -> gspread.Worksheet:
        ws = self._sheets._ensure_tab(STATE_TAB, STATE_HEADERS, as_table=False)
        try:
            if not ws.isSheetHidden:
                ws.hide()
        except gspread.exceptions.APIError:
            pass  # visibility is cosmetic
        return ws

    def load(self) -> dict:
        names: dict[int, str] = {}
        tracked: list[int] = []
        for row in self._worksheet().get_all_values()[1:]:
            if not row or not row[0].strip():
                continue
            topic_id = int(row[0])
            if len(row) > 1 and row[1]:
                names[topic_id] = row[1]
            if len(row) > 2 and row[2].strip().lower() == "yes":
                tracked.append(topic_id)
        return {"names": names, "tracked": tracked}

    def save(self, state: dict) -> None:
        tracked = {int(t) for t in state.get("tracked", [])}
        names = {int(k): str(v) for k, v in state.get("names", {}).items()}
        rows = [
            [str(topic_id), names.get(topic_id, ""), "yes" if topic_id in tracked else ""]
            for topic_id in sorted(names.keys() | tracked)
        ]
        ws = self._worksheet()
        ws.batch_clear([f"A2:C{max(len(rows) + 1, ws.row_count)}"])
        if rows:
            ws.update(values=rows, range_name="A2", raw=True)
