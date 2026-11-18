"""Persistent checkpoints so any crashed or paused run can resume (notebook 07 §3)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from research_system.schemas import ALL_SCHEMAS


def safe_serializer() -> JsonPlusSerializer:
    """Serializer that only deserialises our own schema types (not arbitrary Python objects)."""
    return JsonPlusSerializer(allowed_msgpack_modules=list(ALL_SCHEMAS))


def sqlite_checkpointer(path: Path) -> SqliteSaver:
    """SQLite-backed checkpointer; safe to share across LangGraph worker threads."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    return SqliteSaver(conn, serde=safe_serializer())
