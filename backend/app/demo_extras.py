from __future__ import annotations

from datetime import date

from app.db import connect, migrate
from app.services.extras import primary_hash


def seed_demo_extras() -> None:
    migrate()
    with connect() as conn:
        grok = conn.execute(
            "select id from communities where slug='grok-night-london'"
        ).fetchone()
        shoreditch = conn.execute(
            "select id from communities where slug='shoreditch-builders'"
        ).fetchone()
        if not grok or not shoreditch:
            raise RuntimeError("Demo communities are missing")
        queue = conn.execute(
            """select a.* from applicants a where a.community_id=%s
            and a.status='ask' and a.is_seed order by a.created_at,a.id""",
            (grok["id"],),
        ).fetchall()
        accepted_rows = conn.execute(
            """select a.* from applicants a where a.community_id=%s
            and a.status='accepted' and a.is_seed order by a.created_at,a.id limit 18""",
            (grok["id"],),
        ).fetchall()
        if len(queue) < 2 or not accepted_rows:
            raise RuntimeError("Seed queue or accepted demo applicant is missing")

        first, second = queue[:2]
        accepted = accepted_rows[0]
        identities = {
            "first": primary_hash(first),
            "second": primary_hash(second),
            "accepted": primary_hash(accepted),
        }
        hashes = list({digest for digest in identities.values() if digest})
        demo_communities = [grok["id"], shoreditch["id"]]
        conn.execute(
            "delete from attendance where is_seed and community_id=any(%s)",
            (demo_communities,),
        )
        conn.execute(
            "delete from attendee_likes where is_seed and community_id=any(%s)",
            (demo_communities,),
        )
        conn.execute(
            "delete from attendee_notes where is_seed and identity_hash=any(%s)",
            (hashes,),
        )

        event_dates = {
            2: date(2026, 1, 15),
            3: date(2026, 3, 12),
            4: date(2026, 5, 14),
            5: date(2026, 7, 16),
        }
        attendance_rows = [
            (grok["id"], identities["first"], f"Grok Night London #{number}", event_dates[number], "attended")
            for number in (3, 4, 5)
        ]
        attendance_rows.extend(
            (grok["id"], identities["second"], f"Grok Night London #{number}", event_dates[number], "no_show")
            for number in (4, 5)
        )
        for index, applicant in enumerate(accepted_rows):
            digest = primary_hash(applicant)
            going_back = (index % 3) + 1
            event_numbers = [5, *range(4, 4 - going_back, -1)]
            oldest = min(event_numbers)
            attendance_rows.extend(
                (
                    grok["id"],
                    digest,
                    f"Grok Night London #{number}",
                    event_dates[number],
                    "no_show" if index % 6 == 5 and number == oldest else "attended",
                )
                for number in event_numbers
            )
        attendance_rows.extend(
            (
                grok["id"],
                primary_hash(applicant),
                "Grok Night London #4",
                event_dates[4],
                "attended",
            )
            for applicant in queue[2:]
        )

        like_rows = [
            (grok["id"], primary_hash(accepted_rows[index]))
            for index in (0, 2, 4)
            if index < len(accepted_rows)
        ]
        like_rows.append((grok["id"], identities["first"]))

        with conn.cursor() as cursor:
            cursor.executemany(
                """insert into attendance(community_id,identity_hash,event_name,event_date,status,is_seed)
                values (%s,%s,%s,%s,%s,true)""",
                attendance_rows,
            )
            cursor.executemany(
                """insert into attendee_notes
                (community_id,identity_hash,flag,note,visibility,author,is_seed)
                values (%s,%s,%s,%s,%s,'lead',true)""",
                [
                    (
                        shoreditch["id"], identities["second"], "no_show",
                        "Didn't turn up twice, no message", "shared",
                    ),
                    (grok["id"], identities["second"], "watch", "", "private"),
                    (
                        shoreditch["id"], identities["accepted"], "great_volunteer",
                        "Reliable volunteer who helped other builders", "shared",
                    ),
                ],
            )
            cursor.executemany(
                """insert into attendee_likes(community_id,identity_hash,is_seed)
                values (%s,%s,true) on conflict (community_id,identity_hash) do nothing""",
                like_rows,
            )


if __name__ == "__main__":
    seed_demo_extras()
