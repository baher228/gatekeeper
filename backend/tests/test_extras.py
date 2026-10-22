from datetime import date
from uuid import uuid4

from app.db import as_community, connect
from app.services.blocklist import identifier_hash
from app.services.extras import identity_extras, score_adjustment
from app.services.router import route


def _communities():
    with connect() as conn:
        rows = conn.execute(
            "select id,slug from communities where slug in ('grok-night-london','shoreditch-builders')"
        ).fetchall()
    return {row["slug"]: row["id"] for row in rows}


def _insert_applicant(conn, community_id, label: str):
    email = f"{label}-{uuid4().hex}@example.test"
    row = conn.execute(
        """insert into applicants
        (community_id,name,email,what_build,category,status,decision_source)
        values (%s,%s,%s,'An attendee test project description','builder','accepted','auto')
        returning id,name,email""",
        (community_id, label, email),
    ).fetchone()
    return dict(row)


def _cleanup_applicants(conn, community_id, applicants):
    if not applicants:
        return
    ids = [applicant["id"] for applicant in applicants]
    hashes = [identifier_hash("email", applicant["email"]) for applicant in applicants]
    conn.execute(
        "delete from attendance where community_id=%s and identity_hash=any(%s)",
        (community_id, hashes),
    )
    conn.execute(
        "delete from attendee_likes where community_id=%s and identity_hash=any(%s)",
        (community_id, hashes),
    )
    conn.execute("delete from applicants where id=any(%s)", (ids,))


def test_attendance_adjustment_and_router_score():
    community_id = _communities()["grok-night-london"]
    applicant = {"name": "Attendance test", "email": "attendance-extras@example.test"}
    digest = identifier_hash("email", applicant["email"])
    with connect() as conn:
        with as_community(conn, community_id):
            with conn.cursor() as cursor:
                cursor.executemany(
                    """insert into attendance
                    (community_id,identity_hash,event_name,event_date,status)
                    values (%s,%s,%s,%s,'attended')""",
                    [
                        (community_id, digest, f"Past event {index}", date(2026, index, 1))
                        for index in (1, 2, 3)
                    ],
                )
        extras = identity_extras(conn, community_id, applicant)
        adjustment, reason = score_adjustment(extras["attendance"])
        assert extras["attendance"]["attended"] == 3
        assert adjustment == 0.05
        assert reason == "Attended 3 of your past events"
    base = route(
        {"what_build": "A sufficiently detailed project description for this applicant."},
        [], 0.6, {}, {}, {"remaining": 2},
    )["recommendation"]["final_score"]
    adjusted = route(
        {"what_build": "A sufficiently detailed project description for this applicant."},
        [], 0.6, {}, {}, {"remaining": 2}, adjustment=adjustment,
    )["recommendation"]["final_score"]
    assert adjusted == base + 0.05
    with connect() as conn:
        conn.execute("delete from attendance where identity_hash=%s", (digest,))


def test_private_bans_are_isolated_by_community():
    communities = _communities()
    applicant = {"email": "ban-extras@example.test"}
    digest = identifier_hash("email", applicant["email"])
    with connect() as conn:
        with as_community(conn, communities["grok-night-london"]):
            conn.execute(
                """insert into community_bans
                (community_id,identity_hash,identifier_type,reason)
                values (%s,%s,'email','test ban')""",
                (communities["grok-night-london"], digest),
            )
        assert identity_extras(conn, communities["grok-night-london"], applicant)["ban"]
        assert identity_extras(conn, communities["shoreditch-builders"], applicant)["ban"] is None
        with as_community(conn, communities["shoreditch-builders"]):
            visible = conn.execute("select count(*) as n from community_bans").fetchone()["n"]
            assert visible == 0
        conn.execute("delete from community_bans where identity_hash=%s", (digest,))


def test_private_and_shared_notes_follow_community_visibility():
    communities = _communities()
    applicant = {"email": "notes-extras@example.test"}
    digest = identifier_hash("email", applicant["email"])
    a_id = communities["grok-night-london"]
    b_id = communities["shoreditch-builders"]
    with connect() as conn:
        with as_community(conn, a_id):
            with conn.cursor() as cursor:
                cursor.executemany(
                    """insert into attendee_notes
                    (community_id,identity_hash,flag,note,visibility)
                    values (%s,%s,%s,%s,%s)""",
                    [
                        (a_id, digest, "watch", "private note", "private"),
                        (a_id, digest, "vip", "shared note", "shared"),
                    ],
                )
        a_extras = identity_extras(conn, a_id, applicant)
        b_extras = identity_extras(conn, b_id, applicant)
        assert len(a_extras["own_notes"]) == 2
        assert len(b_extras["shared_notes"]) == 1
        assert b_extras["shared_notes"][0]["note"] == "shared note"
        with as_community(conn, b_id):
            visible = conn.execute(
                "select note from attendee_notes where identity_hash=%s", (digest,)
            ).fetchall()
            assert [row["note"] for row in visible] == ["shared note"]
        conn.execute("delete from attendee_notes where identity_hash=%s", (digest,))


def test_like_unlike_round_trip_updates_applicant_extras(client):
    community_id = _communities()["grok-night-london"]
    with connect() as conn:
        applicant = _insert_applicant(conn, community_id, "Like roundtrip")
    try:
        applicant_id = applicant["id"]
        assert client.get(f"/api/applicants/{applicant_id}").json()["extras"]["liked"] is False
        assert client.post(f"/api/applicants/{applicant_id}/like").json() == {"liked": True}
        assert client.get(f"/api/applicants/{applicant_id}").json()["extras"]["liked"] is True
        assert client.delete(f"/api/applicants/{applicant_id}/like").json() == {"liked": False}
        assert client.get(f"/api/applicants/{applicant_id}").json()["extras"]["liked"] is False

        unknown_id = uuid4()
        assert client.post(f"/api/applicants/{unknown_id}/like").status_code == 404
        assert client.delete(f"/api/applicants/{unknown_id}/like").status_code == 404
    finally:
        with connect() as conn:
            _cleanup_applicants(conn, community_id, [applicant])


def test_attendee_likes_are_isolated_by_community_rls():
    communities = _communities()
    a_id = communities["grok-night-london"]
    b_id = communities["shoreditch-builders"]
    digest = identifier_hash("email", f"like-rls-{uuid4().hex}@example.test")
    with connect() as conn:
        with as_community(conn, a_id):
            conn.execute(
                "insert into attendee_likes(community_id,identity_hash) values (%s,%s)",
                (a_id, digest),
            )
        with as_community(conn, b_id):
            visible = conn.execute(
                "select count(*) as n from attendee_likes where identity_hash=%s",
                (digest,),
            ).fetchone()["n"]
            assert visible == 0
        conn.execute(
            "delete from attendee_likes where community_id=%s and identity_hash=%s",
            (a_id, digest),
        )


def test_applicant_list_includes_bulk_activity_and_filters(client):
    community_id = _communities()["grok-night-london"]
    with connect() as conn:
        applicant = _insert_applicant(conn, community_id, "Applicant list activity")
        digest = identifier_hash("email", applicant["email"])
        with as_community(conn, community_id):
            with conn.cursor() as cursor:
                cursor.executemany(
                    """insert into attendance
                    (community_id,identity_hash,event_name,event_date,status)
                    values (%s,%s,%s,%s,%s)""",
                    [
                        (community_id, digest, "List test attended", date(2026, 8, 1), "attended"),
                        (community_id, digest, "List test no-show", date(2026, 8, 2), "no_show"),
                    ],
                )
            conn.execute(
                "insert into attendee_likes(community_id,identity_hash) values (%s,%s)",
                (community_id, digest),
            )
    try:
        applicant_id = str(applicant["id"])
        all_rows = client.get("/api/communities/grok-night-london/applicants").json()
        row = next(item for item in all_rows if item["id"] == applicant_id)
        assert (row["attended"], row["no_show"], row["liked"]) == (1, 1, True)

        liked_rows = client.get("/api/communities/grok-night-london/applicants?liked=true").json()
        assert applicant_id in {item["id"] for item in liked_rows}
        assert all(item["liked"] for item in liked_rows)

        returning_rows = client.get(
            "/api/communities/grok-night-london/applicants?returning=true"
        ).json()
        assert applicant_id in {item["id"] for item in returning_rows}
        assert all(item["attended"] > 0 for item in returning_rows)
    finally:
        with connect() as conn:
            _cleanup_applicants(conn, community_id, [applicant])


def test_events_group_attendance_and_include_matched_applicants(client):
    community_id = _communities()["grok-night-london"]
    event_name = f"Events test {uuid4().hex}"
    event_date = date(2026, 9, 20)
    with connect() as conn:
        attended = _insert_applicant(conn, community_id, "Event attended")
        no_show = _insert_applicant(conn, community_id, "Event no-show")
        attended_hash = identifier_hash("email", attended["email"])
        no_show_hash = identifier_hash("email", no_show["email"])
        unmatched_hash = identifier_hash("email", f"unmatched-{uuid4().hex}@example.test")
        with as_community(conn, community_id):
            with conn.cursor() as cursor:
                cursor.executemany(
                    """insert into attendance
                    (community_id,identity_hash,event_name,event_date,status)
                    values (%s,%s,%s,%s,%s)""",
                    [
                        (community_id, attended_hash, event_name, event_date, "attended"),
                        (community_id, no_show_hash, event_name, event_date, "no_show"),
                        (community_id, unmatched_hash, event_name, event_date, "no_show"),
                    ],
                )
            conn.execute(
                "insert into attendee_likes(community_id,identity_hash) values (%s,%s)",
                (community_id, attended_hash),
            )
    try:
        response = client.get("/api/communities/grok-night-london/events")
        assert response.status_code == 200, response.text
        event = next(item for item in response.json() if item["event_name"] == event_name)
        assert event["event_date"] == event_date.isoformat()
        assert event["attended"] == 1
        assert event["no_show"] == 2
        assert len(event["attendees"]) == 2
        by_id = {item["applicant_id"]: item for item in event["attendees"]}
        assert by_id[str(attended["id"])]["liked"] is True
        assert by_id[str(no_show["id"])]["liked"] is False
    finally:
        with connect() as conn:
            _cleanup_applicants(conn, community_id, [attended, no_show])
