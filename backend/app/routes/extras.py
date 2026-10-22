from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.db import as_community, connect
from app.schemas import AttendeeNoteIn, BanApplicantIn, CommunityBanIn
from app.services.applications import community_by_slug
from app.services.blocklist import identifier_hash
from app.services.extras import _identifiers, primary_hash

router = APIRouter(prefix="/api")


def _applicant(conn, applicant_id: UUID):
    return conn.execute(
        """select a.*,c.name as community_name,c.slug as community_slug
        from applicants a join communities c on c.id=a.community_id where a.id=%s""",
        (applicant_id,),
    ).fetchone()


def _note(row, community_name: str) -> dict:
    return {
        "id": str(row["id"]),
        "flag": row["flag"],
        "note": row["note"],
        "visibility": row["visibility"],
        "author": row["author"],
        "community_name": community_name,
        "created_at": row["created_at"].isoformat(),
    }


@router.get("/communities/{slug}/bans")
def list_bans(slug: str):
    with connect() as conn:
        community = community_by_slug(conn, slug)
        if not community:
            raise HTTPException(404, "Community not found")
        with as_community(conn, community["id"]):
            rows = conn.execute(
                """select id,identifier_type,label,reason,created_by,created_at
                from community_bans where community_id=%s order by created_at desc""",
                (community["id"],),
            ).fetchall()
        return [
            {
                "id": str(row["id"]),
                "identifier_type": row["identifier_type"],
                "label": row["label"],
                "reason": row["reason"],
                "created_by": row["created_by"],
                "created_at": row["created_at"].isoformat(),
            }
            for row in rows
        ]


@router.post("/applicants/{applicant_id}/ban")
def ban_applicant(applicant_id: UUID, body: BanApplicantIn):
    with connect() as conn:
        applicant = _applicant(conn, applicant_id)
        if not applicant:
            raise HTTPException(404, "Applicant not found")
        count = 0
        with as_community(conn, applicant["community_id"]):
            for kind, value in _identifiers(applicant):
                inserted = conn.execute(
                    """insert into community_bans
                    (community_id,identity_hash,identifier_type,label,reason)
                    values (%s,%s,%s,%s,%s) on conflict (community_id,identity_hash)
                    do nothing returning id""",
                    (
                        applicant["community_id"],
                        identifier_hash(kind, value),
                        kind,
                        applicant["name"],
                        body.reason,
                    ),
                ).fetchone()
                count += int(inserted is not None)
        return {"ok": True, "count": count}


@router.post("/communities/{slug}/bans")
def add_ban(slug: str, body: CommunityBanIn):
    label = f"{body.identifier.strip()[:2]}…"
    with connect() as conn:
        community = community_by_slug(conn, slug)
        if not community:
            raise HTTPException(404, "Community not found")
        with as_community(conn, community["id"]):
            conn.execute(
                """insert into community_bans
                (community_id,identity_hash,identifier_type,label,reason)
                values (%s,%s,%s,%s,%s) on conflict (community_id,identity_hash) do nothing""",
                (
                    community["id"],
                    identifier_hash(body.identifier_type, body.identifier),
                    body.identifier_type,
                    label,
                    body.reason,
                ),
            )
        return {"ok": True}


@router.delete("/communities/{slug}/bans/{ban_id}")
def delete_ban(slug: str, ban_id: UUID):
    with connect() as conn:
        community = community_by_slug(conn, slug)
        if not community:
            raise HTTPException(404, "Community not found")
        with as_community(conn, community["id"]):
            deleted = conn.execute(
                "delete from community_bans where id=%s and community_id=%s returning id",
                (ban_id, community["id"]),
            ).fetchone()
        if not deleted:
            raise HTTPException(404, "Ban not found")
        return {"ok": True}


@router.post("/applicants/{applicant_id}/notes")
def add_note(applicant_id: UUID, body: AttendeeNoteIn):
    with connect() as conn:
        applicant = _applicant(conn, applicant_id)
        if not applicant:
            raise HTTPException(404, "Applicant not found")
        digest = primary_hash(applicant)
        if not digest:
            raise HTTPException(422, "Applicant has no identity to attach a note to")
        with as_community(conn, applicant["community_id"]):
            row = conn.execute(
                """insert into attendee_notes
                (community_id,identity_hash,flag,note,visibility,author)
                values (%s,%s,%s,%s,%s,%s)
                returning id,flag,note,visibility,author,created_at""",
                (
                    applicant["community_id"],
                    digest,
                    body.flag,
                    body.note,
                    body.visibility,
                    body.author,
                ),
            ).fetchone()
        return _note(row, applicant["community_name"])


@router.delete("/applicants/{applicant_id}/notes/{note_id}")
def delete_note(applicant_id: UUID, note_id: UUID):
    with connect() as conn:
        applicant = _applicant(conn, applicant_id)
        if not applicant:
            raise HTTPException(404, "Applicant not found")
        with as_community(conn, applicant["community_id"]):
            deleted = conn.execute(
                "delete from attendee_notes where id=%s and community_id=%s returning id",
                (note_id, applicant["community_id"]),
            ).fetchone()
        if not deleted:
            raise HTTPException(404, "Note not found")
        return {"ok": True}
