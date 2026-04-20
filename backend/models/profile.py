"""Shipping/billing profile — used by tasks at checkout."""

import uuid
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel


class ProfileCreate(BaseModel):
    name: str
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    mobile: str = ""
    address1: str = ""
    address2: str = ""
    city: str = ""
    state: str = ""
    postcode: str = ""
    country: str = "AU"
    flybuys: str = ""


class ProfileUpdate(ProfileCreate):
    name: Optional[str] = None


class Profile(ProfileCreate):
    id: str
    created_at: str

    @classmethod
    def from_row(cls, row) -> "Profile":
        return cls(**dict(row))

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()
