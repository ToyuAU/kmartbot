"""CRUD endpoints for payment cards."""

from fastapi import APIRouter, Depends, HTTPException
from typing import List
import aiosqlite

from backend.database import get_db
from backend.models.card import Card, CardCreate, CardUpdate

router = APIRouter(prefix="/api/cards", tags=["cards"])


@router.get("", response_model=List[Card])
async def list_cards(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM cards ORDER BY created_at DESC") as cur:
        rows = await cur.fetchall()
    return [Card.from_row(r) for r in rows]


@router.get("/{card_id}", response_model=Card)
async def get_card(card_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM cards WHERE id = ?", (card_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Card not found")
    return Card.from_row(row)


@router.post("", response_model=Card, status_code=201)
async def create_card(body: CardCreate, db: aiosqlite.Connection = Depends(get_db)):
    card = Card(id=Card.new_id(), created_at=Card.now(), **body.model_dump())
    await db.execute(
        """INSERT INTO cards
           (id, alias, cardholder, number, expiry_month, expiry_year, cvv, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (card.id, card.alias, card.cardholder, card.number,
         card.expiry_month, card.expiry_year, card.cvv, card.created_at),
    )
    return card


@router.patch("/{card_id}", response_model=Card)
async def update_card(
    card_id: str, body: CardUpdate, db: aiosqlite.Connection = Depends(get_db)
):
    async with db.execute("SELECT * FROM cards WHERE id = ?", (card_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Card not found")

    existing = Card.from_row(row)
    updated = existing.model_copy(update=body.model_dump(exclude_none=True))

    await db.execute(
        """UPDATE cards SET alias=?, cardholder=?, expiry_month=?, expiry_year=?, cvv=?
           WHERE id=?""",
        (updated.alias, updated.cardholder, updated.expiry_month,
         updated.expiry_year, updated.cvv, card_id),
    )
    return updated


@router.delete("/{card_id}", status_code=204)
async def delete_card(card_id: str, db: aiosqlite.Connection = Depends(get_db)):
    await db.execute("DELETE FROM cards WHERE id = ?", (card_id,))
