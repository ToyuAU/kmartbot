"""Payment card model. Stored plain — this runs on a local machine only."""

import uuid
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel


class CardCreate(BaseModel):
    alias: str
    cardholder: str = ""
    number: str
    expiry_month: str
    expiry_year: str
    cvv: str


class CardUpdate(BaseModel):
    alias: Optional[str] = None
    cardholder: Optional[str] = None
    expiry_month: Optional[str] = None
    expiry_year: Optional[str] = None
    cvv: Optional[str] = None


class Card(CardCreate):
    id: str
    created_at: str

    @property
    def masked_number(self) -> str:
        """Returns last 4 digits for display."""
        return f"•••• {self.number[-4:]}" if len(self.number) >= 4 else self.number

    @classmethod
    def from_row(cls, row) -> "Card":
        return cls(**dict(row))

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()
