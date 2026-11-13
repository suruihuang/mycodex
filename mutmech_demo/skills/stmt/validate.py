#!/usr/bin/env python3
"""Deterministic checks for statement-layer mutation records (rules.md next to this script).

Codes are read from the code tables in rules.md, so the tables there stay the single source. Besides field
types and codes, it checks that spans are exact substrings of the quote in order, that records sharing a quote
carry identical statements, and that statement classes, the record class and the label lists follow from the
judgments by the rules.

Usage:
  python3 validate.py records OUT.jsonl [--input DATA.csv] [--id-col ID] [--quote-col Quote]

Problems are printed one per line as "<ID or line>\t<problem>". Exit status is 0 when there are none, 1 otherwise.
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

RULES = Path(__file__).with_name("rules.md")
ADDED = ["statements", "links", "record_class", "mechanism_labels", "context_labels", "inferred_labels",
         "functional_effect", "rationale", "input_flags"]
S_KEYS = ["sid", "span", "kind", "interactions", "interaction_source", "participants", "effect", "effect_of", "certainty"]
L_KEYS = ["sid", "relation", "after_substitution", "applies", "class"]
SITE = {"side_chain", "backbone", "residue_unspecified"}
MAX_STATEMENTS = 15


def codes(section):
    text = RULES.read_text(encoding="utf-8")
    m = re.search(rf"^#{{2,3}} {re.escape(section)}[ \t]*$(.*?)(?=^#{{2,3}} |\Z)", text, re.M | re.S)
    if not m:
        sys.exit(f"rules.md: section '{section}' not found")
    found = re.findall(r"^\|\s*`([a-z_]+)`", m.group(1), re.M)
    if not found:
        sys.exit(f"rules.md: no codes in section '{section}'")
    return set(found)


C = {k: codes(s) for k, s in {
    "kind": "Statement kinds", "label": "Mechanism labels", "source": "Interaction source", "part": "Participants",
    "effect": "Effect", "certainty": "Certainty", "relation": "Relation to the substitution",
    "after": "After the substitution", "applies": "Applies to", "class": "Statement classes", "record": "Record classes"}.items()}


def norm(s):
    return " ".join(s.split())


def load_input(path, id_col):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = list(reader.fieldnames or [])
        if id_col not in header:
            sys.exit(f"{path}: no '{id_col}' column; columns are {header}")
        return {row[id_col].strip(): row for row in reader}, header


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                yield n, None, f"invalid JSON: {e}"
                continue
            yield (n, obj, None) if isinstance(obj, dict) else (n, None, "line is not a JSON object")


def is_str_list(v):
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def expected_class(s, link):
    rel, after, applies = link["relation"], link["after_substitution"], link["applies"]
    if rel == "unrelated" or (not s["interactions"] and applies != "this_mutation"):
        return "context"
    if not s["interactions"]:
        return "effect_only"
    if rel in SITE and after in ("lost", "changed"):
        if applies == "this_mutation":
            return "causal" if s["certainty"] == "asserted" else "proposed_causal"
        if applies == "wild_type":
            return "proposed_causal"
    return "relationship"


def uniq(xs):
    out = []
    for x in xs:
        if x not in out:
            out.append(x)
    return out


def check_statements(st, quote, p):
    """Returns True when the statements are well formed enough to check the links against."""
    if not isinstance(st, list) or not st:
        p("statements must be a non-empty list")
        return False
    if len(st) > MAX_STATEMENTS:
        p(f"{len(st)} statements; at most {MAX_STATEMENTS}")
    ok, pos, q = True, 0, norm(quote) if isinstance(quote, str) else None
    for k, s in enumerate(st, 1):
        if not isinstance(s, dict) or any(f not in s for f in S_KEYS):
            p(f"statement {k}: needs fields {', '.join(S_KEYS)}")
            ok = False
            continue
        w = f"statement {s['sid']}"
        if s["sid"] != f"S{k}":
            p(f"statement {k}: sid must be 'S{k}'")
        if not isinstance(s["span"], str) or not s["span"].strip():
            p(f"{w}: span must be a non-empty string")
        elif q is not None:
            sp = norm(s["span"])
            at = q.find(sp, pos)
            if at >= 0:
                pos = at + len(sp)
            elif sp in q:
                p(f"{w}: span is out of quote order or overlaps the previous span: {s['span'][:60]!r}")
            else:
                p(f"{w}: span not found in the quote: {s['span'][:60]!r}")
        if s["kind"] not in C["kind"]:
            p(f"{w}: unknown kind '{s['kind']}'")
        if not is_str_list(s["interactions"]) or len(set(s["interactions"])) != len(s["interactions"]):
            p(f"{w}: interactions must be a list of distinct label codes")
            ok = False
        else:
            for x in s["interactions"]:
                if x not in C["label"]:
                    p(f"{w}: unknown mechanism label '{x}'")
            if s["interaction_source"] not in C["source"]:
                p(f"{w}: unknown interaction_source '{s['interaction_source']}'")
            elif (s["interaction_source"] == "none") != (not s["interactions"]):
                p(f"{w}: interaction_source is 'none' exactly when interactions is empty")
        if not isinstance(s["participants"], list):
            p(f"{w}: participants must be a list")
        else:
            for x in s["participants"]:
                if not (isinstance(x, dict) and isinstance(x.get("residue"), str) and x["residue"].strip()
                        and isinstance(x.get("chain"), str) and x.get("part") in C["part"]):
                    p(f"{w}: each participant needs residue (non-empty), chain (string) and part ({', '.join(sorted(C['part']))})")
        if s["effect"] not in C["effect"]:
            p(f"{w}: unknown effect '{s['effect']}'")
            ok = False
        if not is_str_list(s["effect_of"]):
            p(f"{w}: effect_of must be a list of strings")
        elif (s["effect"] == "none") != (not s["effect_of"]):
            p(f"{w}: effect_of is empty exactly when effect is 'none'")
        if s["certainty"] not in C["certainty"]:
            p(f"{w}: unknown certainty '{s['certainty']}'")
    return ok


def check_record(rec, quote, p):
    st, links = rec["statements"], rec["links"]
    if not check_statements(st, quote, p):
        return
    if not isinstance(links, list) or len(links) != len(st):
        p("links must be a list with one entry per statement")
        return
    classes = []
    for s, link in zip(st, links):
        if not isinstance(link, dict) or any(f not in link for f in L_KEYS):
            p(f"link for {s['sid']}: needs fields {', '.join(L_KEYS)}")
            return
        w = f"link {s['sid']}"
        if link["sid"] != s["sid"]:
            p(f"{w}: sid '{link['sid']}' out of order")
        bad = [f for f, c in (("relation", "relation"), ("after_substitution", "after"), ("applies", "applies"), ("class", "class")) if link[f] not in C[c]]
        for f in bad:
            p(f"{w}: unknown {f} '{link[f]}'")
        if bad:
            return
        want_applies = {"none": {"none"}, "wild_type_function": {"wild_type"}, "mutation_effect": {"this_mutation", "other_mutation"}}[s["effect"]]
        if link["applies"] not in want_applies:
            p(f"{w}: applies must be {' or '.join(sorted(want_applies))} for effect '{s['effect']}'")
        judged = link["relation"] in SITE and bool(s["interactions"])
        if judged and link["after_substitution"] == "not_applicable":
            p(f"{w}: after_substitution must be judged (relation {link['relation']}, interactions present)")
        if not judged and link["after_substitution"] != "not_applicable":
            p(f"{w}: after_substitution must be 'not_applicable' here")
        exp = expected_class(s, link)
        if link["class"] != exp:
            p(f"{w}: class should be '{exp}' by the rules, not '{link['class']}'")
        classes.append(exp)
    rc = next((r for c, r in (("causal", "causal"), ("proposed_causal", "proposed_causal"), ("relationship", "relationship_only")) if c in classes), "no_mechanism_statement")
    if rec["record_class"] != rc:
        p(f"record_class should be '{rc}' by the rules, not '{rec['record_class']}'")
    mech = uniq([x for c in ("causal", "proposed_causal") for s, k in zip(st, classes) if k == c for x in s["interactions"]])
    ctx = uniq([x for site in (True, False) for s, link, k in zip(st, links, classes)
                if k == "relationship" and (link["relation"] in SITE) == site for x in s["interactions"]])
    if rec["mechanism_labels"] != mech:
        p(f"mechanism_labels should be {mech} by the rules")
    if rec["context_labels"] != ctx:
        p(f"context_labels should be {ctx} by the rules")
    inf = rec["inferred_labels"]
    if not is_str_list(inf) or len(set(inf)) != len(inf) or any(x not in C["label"] for x in inf):
        p("inferred_labels must be a list of distinct label codes")
    elif mech or ctx:
        if inf:
            p("inferred_labels must be empty when mechanism_labels or context_labels is not")
    elif not inf:
        p("inferred_labels must give at least one label when mechanism_labels and context_labels are empty")


def check_records(args, problems):
    rows, header = load_input(args.input, args.id_col) if args.input else ({}, [])
    seen, by_quote = set(), {}
    for n, rec, err in read_jsonl(args.file):
        if err:
            problems.append((f"line {n}", err))
            continue
        if args.id_col not in rec:
            problems.append((f"line {n}", f"missing '{args.id_col}'"))
            continue
        rid = str(rec[args.id_col]).strip()
        p = lambda msg, rid=rid: problems.append((rid, msg))
        if rid in seen:
            p("duplicate ID")
        seen.add(rid)
        if args.input:
            row = rows.get(rid)
            if row is None:
                p("ID not in input file")
            else:
                for col in header:
                    if col != args.id_col and rec.get(col) != row[col]:
                        p(f"supplied field '{col}' missing or differs from input")
        missing = [f for f in ADDED if f not in rec]
        for f in missing:
            p(f"missing field '{f}'")
        if missing:
            continue
        if rec["record_class"] not in C["record"]:
            p(f"unknown record_class '{rec['record_class']}'")
        for f in ("mechanism_labels", "context_labels", "input_flags"):
            if not is_str_list(rec[f]):
                p(f"{f} must be a list of strings")
        for f in ("functional_effect", "rationale"):
            if not isinstance(rec[f], str) or not rec[f].strip():
                p(f"'{f}' must be a non-empty string")
        quote = rec.get(args.quote_col)
        if not isinstance(quote, str):
            p(f"no '{args.quote_col}' string to check spans against")
        else:
            key = norm(quote)
            canon = json.dumps(rec["statements"], sort_keys=True, ensure_ascii=False)
            if key in by_quote and by_quote[key][1] != canon:
                p(f"statements differ from record {by_quote[key][0]}, which has the same quote")
            by_quote.setdefault(key, (rid, canon))
        if is_str_list(rec["mechanism_labels"]) and is_str_list(rec["context_labels"]):
            check_record(rec, quote, p)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["records"])
    ap.add_argument("file")
    ap.add_argument("--input", help="CSV with the supplied fields")
    ap.add_argument("--id-col", default="ID")
    ap.add_argument("--quote-col", default="Quote")
    args = ap.parse_args()
    problems = []
    check_records(args, problems)
    for where, msg in problems:
        print(f"{where}\t{msg}")
    print(f"{len(problems)} problem(s)", file=sys.stderr)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
