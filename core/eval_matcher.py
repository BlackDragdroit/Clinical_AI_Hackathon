"""Calibrate and evaluate the Fellegi–Sunter matcher.

python eval_matcher.py pairs.jsonl            -> weights.json + METRICS_matching.md
Metrics: false-file rate (non-match filed; must be 0), false-reject rate,
review rate, AUC of W, all with 95% bootstrap CIs; plus the README cases (Maria/Max).
"""
from __future__ import annotations

import json
import random
import sys

from fs_matcher import LEVELS, Person, Weights, compare, parse_dob


def load(path: str) -> list[tuple[Person, Person, int]]:
    out = []
    with open(path) as fh:
        for line in fh:
            d = json.loads(line)
            a = Person(d["a_given"], d["a_family"], parse_dob(d["a_dob"]))
            b = Person(d["b_given"], d["b_family"], parse_dob(d["b_dob"]))
            out.append((a, b, int(d["label"])))
    return out


def auc(scores: list[float], labels: list[int]) -> float:
    pos = [s for s, y in zip(scores, labels) if y]
    neg = [s for s, y in zip(scores, labels) if not y]
    if not pos or not neg:
        return float("nan")
    ranked = sorted(zip(scores, labels))
    r, i, s_pos = 0.0, 0, 0.0
    while i < len(ranked):                                # average ranks for ties
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        avg = (i + 1 + j) / 2
        s_pos += sum(avg for k in range(i, j) if ranked[k][1])
        i = j
    return (s_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def rates(decisions, labels, W: Weights) -> dict:
    ff = fr = rv = 0
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    for d, y in zip(decisions, labels):
        if d == "review":
            rv += 1
        elif y and d == "reject":
            fr += 1
        elif not y and d == "file":
            ff += 1
    return {"false_file": ff / max(n_neg, 1), "false_reject": fr / max(n_pos, 1), "review": rv / len(labels)}


def bootstrap(scores, labels, W, fn, n=1000, seed=1) -> dict[str, tuple[float, float, float]]:
    rng = random.Random(seed)
    base = fn(scores, labels, W)
    samples = {k: [] for k in base}
    idx = list(range(len(scores)))
    for _ in range(n):
        sel = [idx[rng.randrange(len(idx))] for _ in idx]
        r = fn([scores[i] for i in sel], [labels[i] for i in sel], W)
        for k in base:
            samples[k].append(r[k])
    out = {}
    for k in base:
        v = sorted(samples[k])
        out[k] = (base[k], v[int(0.025 * n)], v[int(0.975 * n) - 1])
    return out


def main(path: str) -> None:
    pairs = load(path)
    rng = random.Random(3)
    rng.shuffle(pairs)
    cut = int(0.5 * len(pairs))
    train, test = pairs[:cut], pairs[cut:]

    W = Weights.estimate(train)
    tr = [(compare(a, b, W), y) for a, b, y in train]
    tr_labels = [y for _, y in tr]
    # t_file: above every non-match that is not already blocked by the safety rules (+0.5 bit margin)
    # t_reject: below the 1st percentile of matches (-0.5 bit), so clear matches never get rejected
    neg_eligible = [r.score for r, y in tr if not y and r.levels["dob"] == "exact" and r.levels["family"] != "disagree"]
    pos_scores = sorted(r.score for r, y in tr if y)
    # floors: file needs at least 4 bits (odds 16:1 for "same patient"); reject needs at least 6 bits against
    W.t_file = max((max(neg_eligible) if neg_eligible else 0.0) + 0.5, 4.0)
    W.t_reject = min(pos_scores[int(0.01 * len(pos_scores))] - 0.5, -6.0)
    if W.t_reject >= W.t_file:
        W.t_reject = W.t_file - 2.0
    W.save("weights.json")

    te = [compare(a, b, W) for a, b, _ in test]
    te_scores = [r.score for r in te]
    te_dec = [r.decision for r in te]
    te_labels = [y for _, _, y in test]
    ci = bootstrap(te_dec, te_labels, W, rates)
    a_pt = auc(te_scores, te_labels)
    aucs = []
    r2 = random.Random(5)
    for _ in range(1000):
        sel = [r2.randrange(len(test)) for _ in test]
        aucs.append(auc([te_scores[i] for i in sel], [te_labels[i] for i in sel]))
    aucs.sort()

    lines = ["# Patient matching — Fellegi–Sunter", "",
             f"Pairs: {len(train)} train / {len(test)} test (synthetic, labelled). Thresholds: file ≥ {W.t_file:.2f}, reject ≤ {W.t_reject:.2f}.",
             "", "| field | level | m | u | weight (bits) |", "|---|---|---|---|---|"]
    for f, lv, m, u, w in W.table():
        lines.append(f"| {f} | {lv} | {m:.3f} | {u:.3f} | {w:+.2f} |")
    lines += ["", "| metric | value | 95% CI |", "|---|---|---|"]
    for k, (v, lo, hi) in ci.items():
        lines.append(f"| {k} | {v:.4f} | [{lo:.4f}, {hi:.4f}] |")
    lines.append(f"| AUC | {a_pt:.4f} | [{aucs[25]:.4f}, {aucs[974]:.4f}] |")
    lines += ["", "## README scenario cases", "", "| requested | document says | W | decision |", "|---|---|---|---|"]
    maria = Person.from_full("Maria Beispiel", "12 March 1961")
    cases = [("Maria Beispiel", "12 March 1961"), ("Max Beispiel", "1 January 1960"),
             ("Maria Beispeil", "12.03.1961"), ("Maria Beispiel", "03.12.1961"), ("Anna Beispiel", "12 March 1961")]
    for n, d in cases:
        r = compare(maria, Person.from_full(n, d), W)
        lines.append(f"| {maria.display()} | {n}, {d} | {r.score:+.2f} | {r.decision} |")
    open("METRICS_matching.md", "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "pairs.jsonl")
