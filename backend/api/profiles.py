"""CRUD endpoints for shipping/billing profiles."""

from fastapi import APIRouter, Depends, HTTPException, Response
from typing import List
import aiosqlite
from pydantic import BaseModel

from backend.database import get_db
from backend.models.profile import Profile, ProfileCreate, ProfileUpdate
from backend.services.csv_utils import csv_text, parse_csv

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


class CsvImportBody(BaseModel):
    csv: str


@router.get("", response_model=List[Profile])
async def list_profiles(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM profiles ORDER BY created_at DESC") as cur:
        rows = await cur.fetchall()
    return [Profile.from_row(r) for r in rows]


@router.get("/export")
async def export_profiles_csv(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM profiles ORDER BY created_at DESC") as cur:
        rows = await cur.fetchall()
    fieldnames = [
        "name", "first_name", "last_name", "email", "mobile",
        "address1", "address2", "city", "state", "postcode", "country", "flybuys",
    ]
    payload = csv_text((Profile.from_row(r).model_dump() for r in rows), fieldnames)
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="profiles.csv"'},
    )


@router.post("/import", status_code=201)
async def import_profiles_csv(
    body: CsvImportBody,
    db: aiosqlite.Connection = Depends(get_db),
):
    rows = parse_csv(body.csv)
    imported = 0
    for idx, row in enumerate(rows, start=2):
        try:
            profile_in = ProfileCreate(
                name=row.get("name", ""),
                first_name=row.get("first_name", ""),
                last_name=row.get("last_name", ""),
                email=row.get("email", ""),
                mobile=row.get("mobile", ""),
                address1=row.get("address1", ""),
                address2=row.get("address2", ""),
                city=row.get("city", ""),
                state=row.get("state", ""),
                postcode=row.get("postcode", ""),
                country=row.get("country", "") or "AU",
                flybuys=row.get("flybuys", ""),
            )
        except Exception as exc:
            raise HTTPException(400, f"Invalid profile row {idx}: {exc}") from exc
        if not profile_in.name:
            raise HTTPException(400, f'Invalid profile row {idx}: "name" is required')
        profile = Profile(id=Profile.new_id(), created_at=Profile.now(), **profile_in.model_dump())
        await db.execute(
            """INSERT INTO profiles
               (id, name, first_name, last_name, email, mobile,
                address1, address2, city, state, postcode, country, flybuys, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (profile.id, profile.name, profile.first_name, profile.last_name,
             profile.email, profile.mobile, profile.address1, profile.address2,
             profile.city, profile.state, profile.postcode, profile.country,
             profile.flybuys, profile.created_at),
        )
        imported += 1
    return {"imported": imported}


@router.get("/{profile_id}", response_model=Profile)
async def get_profile(profile_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Profile not found")
    return Profile.from_row(row)


@router.post("", response_model=Profile, status_code=201)
async def create_profile(body: ProfileCreate, db: aiosqlite.Connection = Depends(get_db)):
    profile = Profile(id=Profile.new_id(), created_at=Profile.now(), **body.model_dump())
    await db.execute(
        """INSERT INTO profiles
           (id, name, first_name, last_name, email, mobile,
            address1, address2, city, state, postcode, country, flybuys, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (profile.id, profile.name, profile.first_name, profile.last_name,
         profile.email, profile.mobile, profile.address1, profile.address2,
         profile.city, profile.state, profile.postcode, profile.country,
         profile.flybuys, profile.created_at),
    )
    return profile


@router.patch("/{profile_id}", response_model=Profile)
async def update_profile(
    profile_id: str, body: ProfileUpdate, db: aiosqlite.Connection = Depends(get_db)
):
    async with db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Profile not found")

    existing = Profile.from_row(row)
    updates = body.model_dump(exclude_none=True)
    updated = existing.model_copy(update=updates)

    await db.execute(
        """UPDATE profiles SET name=?, first_name=?, last_name=?, email=?, mobile=?,
           address1=?, address2=?, city=?, state=?, postcode=?, country=?, flybuys=?
           WHERE id=?""",
        (updated.name, updated.first_name, updated.last_name, updated.email,
         updated.mobile, updated.address1, updated.address2, updated.city,
         updated.state, updated.postcode, updated.country, updated.flybuys,
         profile_id),
    )
    return updated


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(profile_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute(
        "SELECT name FROM tasks WHERE profile_id = ? ORDER BY created_at DESC LIMIT 4",
        (profile_id,),
    ) as cur:
        rows = await cur.fetchall()
    if rows:
        names = ", ".join((row["name"] or "Unnamed task") for row in rows[:3])
        suffix = "..." if len(rows) > 3 else ""
        raise HTTPException(
            409,
            f"Profile is still assigned to existing tasks ({names}{suffix})",
        )
    await db.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
