"""FR-15: map Telegram forum topics to per-show sheet tabs.

The Bot API cannot look a topic's title up after the fact — the name only
travels on forum_topic_created/edited service messages and on top-level
topic posts (whose reply_to_message is the topic's creation message). So
names are harvested as they are seen and persisted across restarts; a topic
whose name was never seen falls back to "Topic <id>" rather than losing rows.

The bot is opt-in per topic: only topics marked tracked (via /track) are
read at all. The General topic is keyed as id 0.

State lives behind a store object (load() -> dict, save(dict)) because the
bot runs in two homes: locally the state is a JSON file; on Cloud Run the
filesystem is wiped between instances, so the state lives in the spreadsheet
itself (see sheets.SheetTopicStore).
"""

import json
from pathlib import Path

GENERAL_TAB = "General"
GENERAL_TOPIC_ID = 0  # key for messages outside any topic

_FORBIDDEN = set("[]:*?/\\")  # chars Sheets rejects in tab titles
_MAX_TAB_LEN = 80  # Sheets caps tab titles at 100 chars; stay clear of it


def sanitize_tab_title(name: str) -> str:
    cleaned = "".join("-" if c in _FORBIDDEN else c for c in name).strip()
    return cleaned[:_MAX_TAB_LEN].strip() or GENERAL_TAB


class JsonTopicStore:
    """Local persistence: the topic state as a JSON file next to the bot."""

    def __init__(self, cache_file: Path):
        self._cache_file = cache_file

    def load(self) -> dict:
        try:
            raw = json.loads(self._cache_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return {}
        if "names" not in raw:  # pre-/track flat {id: name} schema
            return {"names": raw, "tracked": []}
        return raw

    def save(self, state: dict) -> None:
        self._cache_file.write_text(json.dumps(state, indent=1), encoding="utf-8")


class TopicRegistry:
    """Topic-id → name cache plus the tracked-topic set, mirrored to a store."""

    def __init__(self, store):
        self._store = store
        raw = store.load() or {}
        self._names: dict[int, str] = {int(k): str(v) for k, v in raw.get("names", {}).items()}
        self._tracked: set[int] = {int(t) for t in raw.get("tracked", [])}

    def _save(self) -> None:
        self._store.save({"names": self._names, "tracked": sorted(self._tracked)})

    def is_tracked(self, topic_id: int) -> bool:
        return topic_id in self._tracked

    def track(self, topic_id: int) -> None:
        if topic_id not in self._tracked:
            self._tracked.add(topic_id)
            self._save()

    def untrack(self, topic_id: int) -> None:
        if topic_id in self._tracked:
            self._tracked.discard(topic_id)
            self._save()

    def name_for(self, topic_id: int) -> str | None:
        return self._names.get(topic_id)

    def record(self, topic_id: int, name: str) -> None:
        if self._names.get(topic_id) != name:
            self._names[topic_id] = name
            self._save()

    def observe(self, msg) -> None:
        """Harvest any topic name travelling on this message."""
        if msg.message_thread_id is None:
            return
        edited = msg.forum_topic_edited
        if edited is not None and edited.name:  # icon-only edits carry no name
            self.record(msg.message_thread_id, edited.name)
            return
        created = msg.forum_topic_created or (
            msg.reply_to_message and msg.reply_to_message.forum_topic_created
        )
        if created is not None:
            self.record(msg.message_thread_id, created.name)

    def tab_for(self, msg) -> str:
        if msg.message_thread_id is None:
            return GENERAL_TAB
        self.observe(msg)
        name = self._names.get(msg.message_thread_id)
        return sanitize_tab_title(name) if name else f"Topic {msg.message_thread_id}"
