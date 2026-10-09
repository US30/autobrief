from autobrief import extract
from data.generate import generate
from eval.run_eval import score


def test_generator_is_deterministic_and_owners_are_attendees():
    a, b = generate(10, seed=3), generate(10, seed=3)
    assert a == b and a != generate(10, seed=4)
    for m in a:
        people = extract.participants(m["transcript"])
        assert 2 <= len(m["gold"]["action_items"]) <= 5 and all(g["owner"] in people for g in m["gold"]["action_items"])


def test_perfect_predictions_score_one_and_an_extra_item_costs_precision():
    meetings = generate(5, seed=1)
    perfect = [[g | dict(status="auto_approved") for g in m["gold"]["action_items"]] for m in meetings]
    s = score("gold", meetings, perfect)
    assert (s["precision"], s["recall"], s["f1"], s["due_date_accuracy"]) == (1.0, 1.0, 1.0, 1.0)
    assert s["meetings_needing_no_edit"] == "5/5"
    perfect[0].append(dict(task="Email the CEO", owner="Nobody", due=None, status="needs_review"))
    s = score("gold+1", meetings, perfect)
    assert s["precision"] < 1 and s["recall"] == 1.0 and s["meetings_needing_no_edit"] == "4/5"
    assert s["wrong_items_sent_to_review"] == "1/1"
