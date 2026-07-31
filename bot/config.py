"""Environment configuration. Fails fast if required values are missing."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    google_service_account_file: Path | None  # None -> ambient credentials (Cloud Run)
    spreadsheet_id: str
    allowed_chat_id: int | None  # None until the group ID is known (check_setup helps find it)
    webhook_url: str | None  # set -> webhook mode (Cloud Run); unset -> long polling
    webhook_secret_token: str | None  # Telegram echoes this header; requests without it drop
    port: int  # webhook listen port (Cloud Run injects PORT)


def load_config() -> Config:
    load_dotenv()

    missing = [
        name for name in ("TELEGRAM_BOT_TOKEN", "SPREADSHEET_ID") if not os.getenv(name)
    ]
    if missing:
        raise SystemExit(
            f"Missing required .env values: {', '.join(missing)}. "
            "Copy .env.example to .env and fill them in."
        )

    raw_key_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    key_file = Path(raw_key_file) if raw_key_file else None
    if key_file is not None and not key_file.exists():
        raise SystemExit(f"Service account key file not found: {key_file}")

    webhook_url = os.getenv("WEBHOOK_URL", "").strip() or None
    secret = os.getenv("WEBHOOK_SECRET_TOKEN", "").strip() or None
    if webhook_url and not secret:
        raise SystemExit("WEBHOOK_URL is set but WEBHOOK_SECRET_TOKEN is not — set both.")

    raw_chat_id = os.getenv("ALLOWED_CHAT_ID", "").strip()
    return Config(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        google_service_account_file=key_file,
        spreadsheet_id=os.getenv("SPREADSHEET_ID"),
        allowed_chat_id=int(raw_chat_id) if raw_chat_id else None,
        webhook_url=webhook_url,
        webhook_secret_token=secret,
        port=int(os.getenv("PORT", "8080")),
    )
