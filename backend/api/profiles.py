"""CRUD endpoints for shipping/billing profiles."""

from fastapi import APIRouter, Depends, HTTPException
from typing import List
import aiosqlite

from backend.database import get_db
from backend.models.profile import Profile, ProfileCreate, ProfileUpdate

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.get("", response_model=List[Profile])
async def list_profiles(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM profiles ORDER BY created_at DESC") as cur:
        rows = await cur.fetchall()
    return [Profile.from_row(r) for r in rows]


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
    await db.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
