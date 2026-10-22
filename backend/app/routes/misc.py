from __future__ import annotations

from fastapi import APIRouter, HTTPException
from app.db import as_community, connect
from app.schemas import AppealIn, BlocklistIn, MessageCheckIn, ResolveAppealIn
from app.services.blocklist import identifier_hash
from app.services.applications import community_by_slug
from app.services.history import train_model
from app.services import llm
from app.services.message_classifier import check_message

router = APIRouter(prefix="/api")
CURSOR_MODEL_LABELS = {
    "gemini-3.7-flash-high": "Gemini 3.7 Flash",
    "cursor-grok-4.5-high-fast": "Grok 4.5",
}


def _block_entry(conn, entry_id: str, community_id: str) -> dict | None:
    with as_community(conn, community_id):
        row = conn.execute(
            """select b.*,c.slug as community_slug,c.name as community_name
            from blocklist_entries b join communities c on c.id=b.reporting_community_id
            where b.id=%s""",
            (entry_id,),
        ).fetchone()
        if not row:
            return None
        appeals = conn.execute(
            "select id,contact,message,status,created_at from appeals where entry_id=%s order by created_at",
            (entry_id,),
        ).fetchall()
    return {
        "id": str(row["id"]), "identifier_type": row["identifier_type"],
        "identifier_hash_prefix": row["identifier_hash"][:10], "evidence": row["evidence"],
        "links": row["links"],
        "reporting_community": {"slug": row["community_slug"], "name": row["community_name"]},
        "is_own": str(row["reporting_community_id"]) == str(community_id),
        "status": row["status"], "created_at": row["created_at"],
        "appeals": [
            {"id": str(a["id"]), "contact": a["contact"], "message": a["message"],
             "status": a["status"], "created_at": a["created_at"]}
            for a in appeals
        ],
    }


@router.get("/communities/{slug}/blocklist")
def list_blocklist(slug: str):
    with connect() as conn:
        community = community_by_slug(conn, slug)
        if not community:
            raise HTTPException(404, "Community not found")
        with as_community(conn, community["id"]):
            rows = conn.execute(
                "select id from blocklist_entries order by created_at desc"
            ).fetchall()
        return [
            entry for row in rows
            if (entry := _block_entry(conn, str(row["id"]), str(community["id"])))
        ]


@router.post("/communities/{slug}/blocklist")
def report_block(slug: str, body: BlocklistIn):
    with connect() as conn:
        community = community_by_slug(conn, slug)
        if not community:
            raise HTTPException(404, "Community not found")
        digest = identifier_hash(body.identifier_type, body.identifier)
        with as_community(conn, community["id"]):
            row = conn.execute(
                """insert into blocklist_entries(identifier_hash,identifier_type,evidence,links,
                reporting_community_id,status) values (%s,%s,%s,%s,%s,'pending') returning id""",
                (digest, body.identifier_type, body.evidence, body.links, community["id"]),
            ).fetchone()
        return _block_entry(conn, str(row["id"]), str(community["id"]))


def _set_block_status(slug: str, entry_id: str, status: str):
    with connect() as conn:
        community = community_by_slug(conn, slug)
        if not community:
            raise HTTPException(404, "Community not found")
        with as_community(conn, community["id"]):
            updated = conn.execute(
                "update blocklist_entries set status=%s where id=%s returning id",
                (status, entry_id),
            ).fetchone()
        if not updated:
            raise HTTPException(404, "Blocklist entry not found for this community")
        return _block_entry(conn, str(entry_id), str(community["id"]))


@router.post("/communities/{slug}/blocklist/{entry_id}/confirm")
def confirm_block(slug: str, entry_id: str):
    return _set_block_status(slug, entry_id, "confirmed")


@router.post("/communities/{slug}/blocklist/{entry_id}/remove")
def remove_block(slug: str, entry_id: str):
    return _set_block_status(slug, entry_id, "removed")


@router.get("/communities/{slug}/model")
def get_model(slug: str):
    with connect() as conn:
        community = community_by_slug(conn, slug)
        if not community:
            raise HTTPException(404, "Community not found")
        cid = str(community["id"])
    return train_model(cid)


@router.post("/communities/{slug}/model/retrain")
def retrain(slug: str):
    with connect() as conn:
        community = community_by_slug(conn, slug)
        if not community:
            raise HTTPException(404, "Community not found")
        cid = str(community["id"])
    return train_model(cid)


@router.post("/appeals")
def submit_appeal(body: AppealIn):
    digest = identifier_hash(body.identifier_type, body.identifier)
    with connect() as conn:
        communities = conn.execute("select id from communities").fetchall()
        match = None
        for community in communities:
            with as_community(conn, community["id"]):
                match = conn.execute(
                    """select id,reporting_community_id from blocklist_entries
                    where identifier_hash=%s and status in ('confirmed','appealed')
                    order by created_at desc limit 1""",
                    (digest,),
                ).fetchone()
            if match:
                break
        if not match:
            return {"id": None, "status": None, "matched": False}
        with as_community(conn, match["reporting_community_id"]):
            conn.execute(
                "update blocklist_entries set status='appealed' where id=%s",
                (match["id"],),
            )
            appeal = conn.execute(
                """insert into appeals(entry_id,contact,message,status) values (%s,%s,%s,'open')
                returning id,status""",
                (match["id"], body.contact, body.message),
            ).fetchone()
        return {"id": str(appeal["id"]), "status": appeal["status"], "matched": True}


@router.post("/communities/{slug}/appeals/{appeal_id}/resolve")
def resolve_appeal(slug: str, appeal_id: str, body: ResolveAppealIn):
    with connect() as conn:
        community = community_by_slug(conn, slug)
        if not community:
            raise HTTPException(404, "Community not found")
        with as_community(conn, community["id"]):
            appeal = conn.execute(
                """select a.id,a.entry_id from appeals a join blocklist_entries b on b.id=a.entry_id
                where a.id=%s and b.reporting_community_id=%s""",
                (appeal_id, community["id"]),
            ).fetchone()
            if not appeal:
                raise HTTPException(404, "Appeal not found for this community")
            status = "removed" if body.outcome == "upheld" else "confirmed"
            conn.execute("update blocklist_entries set status=%s where id=%s", (status, appeal["entry_id"]))
        conn.execute("update appeals set status=%s where id=%s", (body.outcome, appeal_id))
        return _block_entry(conn, str(appeal["entry_id"]), str(community["id"]))


@router.get("/eval")
def get_eval():
    from app.eval import REPORT_PATH
    import json
    if not REPORT_PATH.exists():
        raise HTTPException(404, "No evaluation report has been generated")
    return json.loads(REPORT_PATH.read_text())


@router.post("/eval/run")
def run_eval():
    from app.eval import run
    return run()


@router.post("/messages/check")
async def message_check(body: MessageCheckIn):
    try:
        return await check_message(body.text)
    except RuntimeError as exc:
        raise HTTPException(503, "SMS spam model unavailable") from exc


@router.get("/health")
def health():
    import os
    try:
        with connect() as conn:
            conn.execute("select 1")
        db_ok = True
    except Exception:
        db_ok = False
    settings = llm.config()
    llm_error = llm.last_error
    if llm_error is None:
        if not settings["configured"]:
            llm_error = llm.configuration_error(settings)
        elif llm.last_ok is None:
            llm_error = "not yet verified – no LLM call made since startup"
    label = (
        f"{CURSOR_MODEL_LABELS.get(settings['model'], settings['model'])} via Cursor"
        if settings["provider"] == "cursor"
        else f"{settings['provider']} · {settings['model']}"
    )
    return {
        "ok": db_ok, "db": "connected" if db_ok else "unavailable",
        "llm": {
            "available": bool(settings["configured"] and llm.last_ok is True),
            "provider": settings["provider"],
            "model": settings["model"],
            "label": label,
            "verified": llm.last_ok is not None,
            "error": llm_error,
            "calls_made": llm.calls_made,
            "max_calls": llm.MAX_CALLS,
        },
        "github_token": bool(os.getenv("GITHUB_TOKEN")),
    }
