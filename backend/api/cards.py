"""CRUD endpoints for payment cards."""

from fastapi import APIRouter, Depends, HTTPException, Response
from typing import List
import aiosqlite
from pydantic import BaseModel

from backend.database import get_db
from backend.models.card import Card, CardCreate, CardUpdate
from backend.services.csv_utils import csv_text, parse_csv

router = APIRouter(prefix="/api/cards", tags=["cards"])


class CsvImportBody(BaseModel):
    csv: str


@router.get("", response_model=List[Card])
async def list_cards(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM cards ORDER BY created_at DESC") as cur:
        rows = await cur.fetchall()
    return [Card.from_row(r) for r in rows]


@router.get("/export")
async def export_cards_csv(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM cards ORDER BY created_at DESC") as cur:
        rows = await cur.fetchall()
    fieldnames = ["alias", "cardholder", "number", "expiry_month", "expiry_year", "cvv"]
    payload = csv_text((Card.from_row(r).model_dump() for r in rows), fieldnames)
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="cards.csv"'},
    )


@router.post("/import", status_code=201)
async def import_cards_csv(
    body: CsvImportBody,
    db: aiosqlite.Connection = Depends(get_db),
):
    rows = parse_csv(body.csv)
    imported = 0
    for idx, row in enumerate(rows, start=2):
        try:
            card_in = CardCreate(
                alias=row.get("alias", ""),
                cardholder=row.get("cardholder", ""),
                number=row.get("number", ""),
                expiry_month=row.get("expiry_month", ""),
                expiry_year=row.get("expiry_year", ""),
                cvv=row.get("cvv", ""),
            )
        except Exception as exc:
            raise HTTPException(400, f"Invalid card row {idx}: {exc}") from exc
        if not card_in.alias or not card_in.number:
            raise HTTPException(400, f'Invalid card row {idx}: "alias" and "number" are required')
        card = Card(id=Card.new_id(), created_at=Card.now(), **card_in.model_dump())
        await db.execute(
            """INSERT INTO cards
               (id, alias, cardholder, number, expiry_month, expiry_year, cvv, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (card.id, card.alias, card.cardholder, card.number,
             card.expiry_month, card.expiry_year, card.cvv, card.created_at),
        )
        imported += 1
    return {"imported": imported}


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
