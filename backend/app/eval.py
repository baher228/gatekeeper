from __future__ import annotations

import json
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from app.db import connect
from app.services.history import BASE_FEATURES, feature_vector, fit, predict_from_model
from app.services.rules import calculate_rule_score, heuristic_checks
from app.services.router import route
from app.synthetic import EVAL_KIND_COUNTS, lead_label, make_applicant

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
TESTSET_PATH = DATA_DIR / "testset.json"
REPORT_PATH = DATA_DIR / "eval_report.json"


def generate_testset() -> list[dict]:
    rng = random.Random(2026)
    items = []
    for kind, count in EVAL_KIND_COUNTS.items():
        for _ in range(count):
            applicant = make_applicant(rng, kind)
            items.append({
                **applicant,
                "id": f"eval-{len(items) + 1:03}",
                "label": lead_label(applicant, rng),
                "tag": kind,
                "blocklist": [],
            })
    rng.shuffle(items)
    scammer_ids = [item["id"] for item in items if item["kind"] == "scammer"]
    blocklisted_ids = set(rng.sample(scammer_ids, len(scammer_ids) // 2))
    for item in items:
        if item["id"] in blocklisted_ids:
            item["blocklist"] = [
                {
                    "entry_id": "synthetic-confirmed",
                    "identifier_type": "handle",
                    "status": "confirmed",
                    "reporting_community": "Synthetic test community",
                    "evidence": "Synthetic fixture",
                    "links": [],
                    "reported_at": None,
                }
            ]
    TESTSET_PATH.write_text(json.dumps(items, indent=2) + "\n")
    return items


def _seed_history_model(community_id: str, categories: list[str]):
    with connect() as conn:
        rows = conn.execute(
            """select features,verdict from decisions where community_id=%s and source='seed'
            and is_seed=true and verdict in ('accept','decline') order by created_at""",
            (community_id,),
        ).fetchall()
    feature_names = BASE_FEATURES + [f"category_{category}" for category in categories]
    return fit(rows, feature_names), feature_names, len(rows)


def _normalized_outcome(status: str) -> str:
    if status in ("accepted", "waitlisted"):
        return "accept"
    if status == "declined":
        return "decline"
    return "ask"


def _metrics(
    name: str,
    items: list[dict],
    outcomes: list[str],
    n_train: int,
) -> dict:
    tp_a = sum(
        item["label"] == "accept" and outcome in ("accepted", "waitlisted")
        for item, outcome in zip(items, outcomes)
    )
    fp_a = sum(
        item["label"] == "decline" and outcome in ("accepted", "waitlisted")
        for item, outcome in zip(items, outcomes)
    )
    fn_a = sum(
        item["label"] == "accept" and outcome == "declined"
        for item, outcome in zip(items, outcomes)
    )
    tp_d = sum(
        item["label"] == "decline" and outcome == "declined"
        for item, outcome in zip(items, outcomes)
    )
    fp_d = sum(
        item["label"] == "accept" and outcome == "declined"
        for item, outcome in zip(items, outcomes)
    )
    fn_d = sum(
        item["label"] == "decline" and outcome in ("accepted", "waitlisted")
        for item, outcome in zip(items, outcomes)
    )
    correct = sum(
        item["label"] == _normalized_outcome(outcome)
        for item, outcome in zip(items, outcomes)
    )
    n_accept = sum(item["label"] == "accept" for item in items)
    confusion_matrix = {
        label: {"accept": 0, "ask": 0, "decline": 0}
        for label in ("accept", "decline")
    }
    for item, outcome in zip(items, outcomes):
        confusion_matrix[item["label"]][_normalized_outcome(outcome)] += 1
    by_kind = {}
    for kind in EVAL_KIND_COUNTS:
        selected = [
            (item, outcome)
            for item, outcome in zip(items, outcomes)
            if item["kind"] == kind
        ]
        by_kind[kind] = {
            "n": len(selected),
            "accuracy": sum(
                item["label"] == _normalized_outcome(outcome)
                for item, outcome in selected
            ) / max(1, len(selected)),
            "ask_rate": sum(outcome == "ask" for _, outcome in selected)
            / max(1, len(selected)),
        }
    return {
        "name": name,
        "n": len(items),
        "n_train": n_train,
        "accuracy": correct / max(1, len(items)),
        "accuracy_on_decided": (
            sum(
                item["label"] == _normalized_outcome(outcome)
                for item, outcome in zip(items, outcomes)
                if outcome != "ask"
            )
            / max(1, sum(outcome != "ask" for outcome in outcomes))
        ),
        "accept_precision": tp_a / max(1, tp_a + fp_a),
        "accept_recall": tp_a / max(1, tp_a + fn_a),
        "decline_precision": tp_d / max(1, tp_d + fp_d),
        "decline_recall": tp_d / max(1, tp_d + fn_d),
        "false_block_rate": fp_d / max(1, n_accept),
        "ask_rate": sum(outcome == "ask" for outcome in outcomes) / max(1, len(outcomes)),
        "confusion": {
            "accept_tp": tp_a,
            "accept_fp": fp_a,
            "accept_fn": fn_a,
            "decline_tp": tp_d,
            "decline_fp": fp_d,
            "decline_fn": fn_d,
            "ask": sum(outcome == "ask" for outcome in outcomes),
        },
        "confusion_matrix": confusion_matrix,
        "by_kind": by_kind,
    }


def run() -> dict:
    DATA_DIR.mkdir(exist_ok=True)
    items = generate_testset()
    with connect() as conn:
        community = conn.execute(
            "select id,rules from communities where slug='grok-night-london'"
        ).fetchone()
        if not community:
            raise RuntimeError("Run app.seed before evaluation")
        community_id = str(community["id"])
        categories = [
            row["slug"]
            for row in conn.execute(
                "select slug from categories where community_id=%s order by slug",
                (community_id,),
            ).fetchall()
        ]
        seed_emails = {
            row["email"]
            for row in conn.execute(
                "select email from applicants where community_id=%s and is_seed=true",
                (community_id,),
            ).fetchall()
        }
    test_emails = {item["email"] for item in items}
    overlap = test_emails & seed_emails
    assert not overlap, f"Test and seed emails overlap: {sorted(overlap)}"

    model, feature_names, n_training = _seed_history_model(community_id, categories)
    if model is None or n_training != 120:
        raise RuntimeError(
            f"Expected 120 seed history decisions for evaluation; found {n_training}"
        )
    outcomes = {"rules_only": [], "rules_plus_history": []}
    for item in items:
        evidence = item["evidence"]
        checks = heuristic_checks(community["rules"], item, evidence)
        score = calculate_rule_score(checks, evidence, item["category"])
        quota = {
            "slug": item["category"],
            "quota": 100000,
            "used": 0,
            "remaining": 100000,
            "waitlisted": 0,
            "bypass_quota": True,
        }
        base_history = {
            "available": False,
            "p_accept": None,
            "n_training": 0,
            "top_features": [],
        }
        no_history = route(
            item, checks, score, evidence, base_history, quota, item["blocklist"]
        )
        outcomes["rules_only"].append(no_history["status"])

        vector = feature_vector(
            item, {"rule_score": score, "rule_checks": checks}, evidence, categories
        )
        history = predict_from_model(model, feature_names, vector, n_training)
        with_history = route(
            item, checks, score, evidence, history, quota, item["blocklist"]
        )
        outcomes["rules_plus_history"].append(with_history["status"])

    variants = [
        _metrics(
            name,
            items,
            outcomes[name],
            n_training if name == "rules_plus_history" else 0,
        )
        for name in ("rules_only", "rules_plus_history")
    ]
    edge_cases = []
    for kind in EVAL_KIND_COUNTS:
        kind_items = [item for item in items if item["kind"] == kind]
        labels = Counter(item["label"] for item in kind_items)
        edge_cases.append({
            "kind": kind,
            "label_distribution": {
                "accept": labels.get("accept", 0),
                "decline": labels.get("decline", 0),
            },
            "rules_only_accuracy": next(
                variant["by_kind"][kind]["accuracy"]
                for variant in variants if variant["name"] == "rules_only"
            ),
            "rules_plus_history_accuracy": next(
                variant["by_kind"][kind]["accuracy"]
                for variant in variants if variant["name"] == "rules_plus_history"
            ),
        })
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_train": n_training,
        "test_set": {
            "n": len(items),
            "n_accept": sum(item["label"] == "accept" for item in items),
            "n_decline": sum(item["label"] == "decline" for item in items),
            "n_scam": sum(item["kind"] == "scammer" for item in items),
            "n_edge": sum(
                item["kind"] in (
                    "first_timer_concrete",
                    "researcher_paper",
                    "new_account_polished",
                )
                for item in items
            ),
            "source": "make_applicant(random.Random(2026)); labels from lead_label.",
        },
        "train_set": {
            "n": n_training,
            "source": "120 seed decisions from make_applicant(random.Random(42)).",
        },
        "variants": variants,
        "notes": [
            "Synthetic lead policy: accept strong builders, concrete first-timers, and researchers; decline vague, new-account, recruiter/seller, and scammer applications.",
            "Held-out applicants use random.Random(2026); training applicants use random.Random(42).",
            "Both variants use heuristic rule checks; no LLM calls were made.",
            "Labels include 8% noise from the synthetic lead policy.",
            "Ask counts as incorrect in overall accuracy and is excluded from accuracy_on_decided.",
            "Thresholds were not tuned using the held-out test set.",
            "Exactly half of the scammer examples have a confirmed blocklist match.",
        ],
        "edge_cases": edge_cases,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n")
    print(
        "variant              accuracy  acc.decided  accept P/R  decline P/R"
        "  false-block  ask-rate  n_train"
    )
    for variant in variants:
        print(
            f"{variant['name']:20} {variant['accuracy']:.3f}     "
            f"{variant['accuracy_on_decided']:.3f}      "
            f"{variant['accept_precision']:.3f}/{variant['accept_recall']:.3f}   "
            f"{variant['decline_precision']:.3f}/{variant['decline_recall']:.3f}      "
            f"{variant['false_block_rate']:.3f}       {variant['ask_rate']:.3f}     "
            f"{variant['n_train']}"
        )
    print("kind                    n  labels accept/decline  rules_only  rules_plus_history")
    for row in edge_cases:
        labels = row["label_distribution"]
        print(
            f"{row['kind']:24} {sum(labels.values()):2}  "
            f"{labels['accept']:2}/{labels['decline']:<2}               "
            f"{row['rules_only_accuracy']:.3f}       "
            f"{row['rules_plus_history_accuracy']:.3f}"
        )
    return report


if __name__ == "__main__":
    run()
