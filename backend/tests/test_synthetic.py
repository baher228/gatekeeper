import random

from app.eval import _metrics
from app.synthetic import lead_label, make_applicant


def test_lead_label_is_deterministic_for_fixed_random_state():
    applicant = make_applicant(random.Random(42), "strong_builder")

    first = lead_label(applicant, random.Random(2026))
    second = lead_label(applicant, random.Random(2026))

    assert first == second


def test_eval_metrics_include_verdict_confusion_and_kind_breakdown():
    items = [
        {"kind": "strong_builder", "label": "accept"},
        {"kind": "strong_builder", "label": "accept"},
        {"kind": "weak_vague", "label": "decline"},
        {"kind": "scammer", "label": "decline"},
    ]
    outcomes = ["accepted", "waitlisted", "ask", "declined"]
    result = _metrics("rules_only", items, outcomes, 0)

    assert result["confusion_matrix"] == {
        "accept": {"accept": 2, "ask": 0, "decline": 0},
        "decline": {"accept": 0, "ask": 1, "decline": 1},
    }
    assert result["by_kind"]["strong_builder"] == {
        "n": 2,
        "accuracy": 1.0,
        "ask_rate": 0.0,
    }
    assert result["by_kind"]["weak_vague"]["ask_rate"] == 1.0
    assert result["n_train"] == 0
