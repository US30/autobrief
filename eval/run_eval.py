"""Score extraction against the generator's ground truth. Writes eval/report.md.

Usage: python eval/run_eval.py [--n 40] [--seed 7] [--no-llm]

A predicted item matches a gold item when the task text is similar and the owner is the same.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
from rapidfuzz import fuzz  # noqa: E402

from autobrief import extract, graph, llm  # noqa: E402
from autobrief.schema import Meeting  # noqa: E402
from data.generate import generate  # noqa: E402

TASK_SIM = 60
MIN_SAVED_PER_MEETING = 12.0  # assumption: writing up and filing follow-ups by hand; an estimate, not a measurement


def match(pred: list[dict], gold: list[dict]) -> list[tuple[dict, dict]]:
    """Greedy one-to-one pairing on task-text similarity, best pairs first."""
    pairs = sorted(((fuzz.token_set_ratio(p["task"].lower(), g["task"].lower()), i, j)
                    for i, p in enumerate(pred) for j, g in enumerate(gold)), reverse=True)
    used_p, used_g, out = set(), set(), []
    for sim, i, j in pairs:
        if sim >= TASK_SIM and i not in used_p and j not in used_g:
            used_p.add(i); used_g.add(j)
            out.append((pred[i], gold[j]))
    return out


def score(name: str, meetings: list[dict], preds: list[list[dict]]) -> dict:
    tp = n_pred = n_gold = due_ok = clean = wrong = wrong_caught = right = right_auto = 0
    for m, pred in zip(meetings, preds):
        gold = m["gold"]["action_items"]
        pairs = match(pred, gold)
        good = [(p, g) for p, g in pairs if p["owner"] == g["owner"]]
        good_ids = {id(p) for p, _ in good}
        tp += len(good); n_pred += len(pred); n_gold += len(gold)
        due_ok += sum(p["due"] == g["due"] for p, g in good)
        clean += len(good) == len(pred) == len(gold) and all(p["due"] == g["due"] for p, g in good)
        for p in pred:  # does the review step catch the wrong ones and let the right ones through?
            if id(p) in good_ids:
                right += 1; right_auto += p["status"] == "auto_approved"
            else:
                wrong += 1; wrong_caught += p["status"] == "needs_review"
    prec, rec = tp / max(n_pred, 1), tp / max(n_gold, 1)
    return dict(extractor=name, meetings=len(meetings), gold_items=n_gold, predicted=n_pred,
                precision=round(prec, 3), recall=round(rec, 3), f1=round(2 * prec * rec / max(prec + rec, 1e-9), 3),
                due_date_accuracy=round(due_ok / max(tp, 1), 3), meetings_needing_no_edit=f"{clean}/{len(meetings)}",
                wrong_items_sent_to_review=f"{wrong_caught}/{wrong}", correct_items_auto_approved=f"{right_auto}/{right}")


def predict(meetings: list[dict], use_llm: bool) -> list[list[dict]]:
    """Predictions per meeting. Stops at the first API failure, so the result may cover only the first meetings."""
    out = []
    for n, m in enumerate(meetings, 1):
        mt = Meeting(title=m["title"], date=m["date"], transcript=m["transcript"])
        ex = extract.llm_extract(mt) if use_llm else extract.rule_extract(mt)
        if ex is None:
            print(f"[{n}/{len(meetings)}] API error: {llm.last_error}", flush=True)
            break
        out.append(graph.check_items(mt, ex, "llm"))  # same checks for both, so the review columns are comparable
        if use_llm:
            print(f"[{n}/{len(meetings)}] {len(out[-1])} items", flush=True)
    return out


def main(n: int, seed: int, use_llm: bool):
    meetings = generate(n, seed)
    rows = [score("regex baseline", meetings, predict(meetings, use_llm=False))]
    note = "LLM not run (no OPENAI_API_KEY or --no-llm)."
    if use_llm and llm.available():
        preds = predict(meetings, use_llm=True)
        if preds:
            n = len(preds)  # fewer than asked if the API stopped answering; both rows then cover the same meetings
            rows = [score("regex baseline", meetings[:n], predict(meetings[:n], use_llm=False)),
                    score(llm.model_name(), meetings[:n], preds)]
            clean = int(rows[-1]["meetings_needing_no_edit"].split("/")[0])
            note = (f"Estimated time saved: {clean} of {n} meetings needed no edit; at an assumed {MIN_SAVED_PER_MEETING:.0f} "
                    f"minutes of manual write-up per meeting that is about {clean * MIN_SAVED_PER_MEETING / 60:.1f} hours "
                    f"over this set. The minutes figure is an assumption, not a measurement.")
        else:
            note = f"LLM run failed: `{llm.last_error}`"
    if n < len(meetings):
        note += f" The API failed after {n} of {len(meetings)} meetings (`{llm.last_error}`), so only those are scored."
    out = [f"# AutoBrief evaluation (seed {seed}, {n} synthetic meetings)\n", pd.DataFrame(rows).set_index("extractor").T.to_markdown(), "",
           "A predicted item counts as correct when its task text matches a gold item and the owner is the same. "
           "Due-date accuracy is measured on correct items. A meeting needs no edit when every item, owner and "
           "due date is right and nothing is missing or extra.\n", note, "",
           "Transcripts are template-generated, so they are cleaner than real meetings. Treat these numbers as a check "
           "that the pipeline works, not as accuracy on real calls."]
    (ROOT / "eval" / "report.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=40)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--no-llm", action="store_true")
    a = p.parse_args()
    main(a.n, a.seed, not a.no_llm)
