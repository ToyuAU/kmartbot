"""Helpers for CSV import/export across local CRUD resources."""

from __future__ import annotations

import csv
import io
from typing import Iterable


def csv_text(rows: Iterable[dict[str, object]], fieldnames: list[str]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({name: row.get(name, "") for name in fieldnames})
    return buf.getvalue()


def parse_csv(text: str) -> list[dict[str, str]]:
    cleaned = text.lstrip("\ufeff").strip()
    if not cleaned:
        return []
    reader = csv.DictReader(io.StringIO(cleaned))
    if not reader.fieldnames:
        return []
    rows: list[dict[str, str]] = []
    for row in reader:
        rows.append({(k or "").strip(): (v or "").strip() for k, v in row.items()})
    return rows


def parse_bool(value: str, default: bool = False) -> bool:
    cleaned = value.strip().lower()
    if not cleaned:
        return default
    if cleaned in {"1", "true", "yes", "y", "on"}:
        return True
    if cleaned in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value}")


def split_pipe(value: str) -> list[str]:
    return [part.strip() for part in value.split("|") if part.strip()]
