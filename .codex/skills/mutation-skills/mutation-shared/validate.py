#!/usr/bin/env python3
"""Deterministic checks for mutation extraction records and review verdicts.

Codes for evidence scopes, mechanism labels, and evidence basis are read from
rules.md next to this script, so the tables there stay the single source.

Usage:
  python3 validate.py records OUT.jsonl [--input DATA.csv] [--id-col ID] [--quote-col Quote]
  python3 validate.py review REVIEW.jsonl --input DATA.csv [--id-col ID] [--quote-col Quote]

Problems are printed one per line as "<ID or line>\t<problem>".
Exit status is 0 when there are none, 1 otherwise.
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

RULES = Path(__file__).with_name("rules.md")
ADDED_FIELDS = [
    "evidence_scope", "mechanism_labels", "mechanism", "evidence_basis",
    "evidence_spans", "supporting_evidence", "functional_effect",
    "uncertainty", "input_flags",
]
TEXT_FIELDS = ["mechanism", "supporting_evidence", "functional_effect", "uncertainty"]
VERDICTS = {"accept", "revise", "needs_human"}
ISSUE_FIELDS = ["error_type", "field", "issue", "cite", "suggested_correction"]


def codes(section):
    text = RULES.read_text(encoding="utf-8")
    m = re.search(rf"^## {re.escape(section)}[ \t]*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        sys.exit(f"rules.md: section '{section}' not found")
    found = re.findall(r"^\|\s*`([a-z_]+)`", m.group(1), re.M)
    if not found:
        sys.exit(f"rules.md: no codes in section '{section}'")
    return set(found)


def norm(s):
    return " ".join(s.split())


def contains(haystack, needle):
    return needle in haystack or norm(needle) in norm(haystack)


def load_input(path, id_col):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = list(reader.fieldnames or [])
        if id_col not in header:
            sys.exit(f"{path}: no '{id_col}' column; columns are {header}")
        rows = {}
        for row in reader:
            rows[row[id_col].strip()] = row
    return rows, header


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
            if not isinstance(obj, dict):
                yield n, None, "line is not a JSON object"
                continue
            yield n, obj, None


def is_str_list(v):
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def check_records(args, problems):
    scopes = codes("Evidence scope")
    labels = codes("Mechanism labels")
    bases = codes("Evidence basis")
    rows, header = load_input(args.input, args.id_col) if args.input else ({}, [])
    seen = set()

    for n, rec, err in read_jsonl(args.file):
        if err:
            problems.append((f"line {n}", err))
            continue
        if args.id_col not in rec:
            problems.append((f"line {n}", f"missing '{args.id_col}'"))
            continue
        rid = str(rec[args.id_col]).strip()
        p = lambda msg: problems.append((rid, msg))

        if rid in seen:
            p("duplicate ID")
        seen.add(rid)

        if args.input:
            row = rows.get(rid)
            if row is None:
                p("ID not in input file")
            else:
                for col in header:
                    if col == args.id_col:
                        continue
                    if col not in rec:
                        p(f"supplied field '{col}' missing")
                    elif rec[col] != row[col]:
                        p(f"supplied field '{col}' differs from input")

        missing = [f for f in ADDED_FIELDS if f not in rec]
        for f in missing:
            p(f"missing field '{f}'")
        if missing:
            continue

        scope, basis, labs = rec["evidence_scope"], rec["evidence_basis"], rec["mechanism_labels"]
        if scope not in scopes:
            p(f"unknown evidence_scope '{scope}'")
        if basis not in bases:
            p(f"unknown evidence_basis '{basis}'")
        if not is_str_list(labs) or not labs:
            p("mechanism_labels must be a non-empty list of strings")
            labs = []
        for lab in labs:
            if lab not in labels:
                p(f"unknown mechanism label '{lab}'")
        if len(labs) != len(set(labs)):
            p("repeated mechanism label")
        if basis == "not_assessable" and labs != ["not_stated"]:
            p("not_assessable requires mechanism_labels == ['not_stated']")
        if "not_stated" in labs and basis != "not_assessable":
            p("'not_stated' label requires evidence_basis 'not_assessable'")
        if basis == "structure_inference" and scope != "structure_assisted":
            p("structure_inference is only allowed under structure_assisted")

        for f in TEXT_FIELDS:
            if not isinstance(rec[f], str) or not rec[f].strip():
                p(f"'{f}' must be a non-empty string")
        if not is_str_list(rec["input_flags"]):
            p("input_flags must be a list of strings")

        spans = rec["evidence_spans"]
        quote = rec.get(args.quote_col)
        if not is_str_list(spans):
            p("evidence_spans must be a list of strings")
        elif not spans and basis != "not_assessable":
            p("evidence_spans is empty")
        elif not isinstance(quote, str):
            p(f"no '{args.quote_col}' string to check evidence_spans against")
        else:
            for s in spans:
                if not s.strip():
                    p("empty evidence span")
                elif not contains(quote, s):
                    p(f"evidence span not found in {args.quote_col}: {s[:60]!r}")


def check_review(args, problems):
    rows, header = load_input(args.input, args.id_col)
    seen = set()

    for n, rec, err in read_jsonl(args.file):
        if err:
            problems.append((f"line {n}", err))
            continue
        if args.id_col not in rec:
            problems.append((f"line {n}", f"missing '{args.id_col}'"))
            continue
        rid = str(rec[args.id_col]).strip()
        p = lambda msg: problems.append((rid, msg))

        if rid in seen:
            p("duplicate ID")
        seen.add(rid)
        row = rows.get(rid)
        if row is None:
            p("ID not in input file")
        supplied = "\n".join(v for v in (row or {}).values() if isinstance(v, str))

        verdict = rec.get("verdict")
        if verdict not in VERDICTS:
            p(f"verdict must be one of {sorted(VERDICTS)}")
        issues = rec.get("issues")
        if not isinstance(issues, list):
            p("issues must be a list")
            continue
        if verdict in ("revise", "needs_human") and not issues:
            p(f"verdict '{verdict}' needs at least one issue")

        for i, iss in enumerate(issues):
            if not isinstance(iss, dict):
                p(f"issue {i} is not an object")
                continue
            for f in ISSUE_FIELDS:
                if not isinstance(iss.get(f), str) or not iss[f].strip():
                    p(f"issue {i}: '{f}' must be a non-empty string")
            cite = iss.get("cite")
            if row is not None and isinstance(cite, str) and cite.strip() and not contains(supplied, cite):
                p(f"issue {i}: cite not found in supplied fields: {cite[:60]!r}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["records", "review"])
    ap.add_argument("file")
    ap.add_argument("--input", help="CSV with the supplied fields (required for review)")
    ap.add_argument("--id-col", default="ID")
    ap.add_argument("--quote-col", default="Quote")
    args = ap.parse_args()
    if args.mode == "review" and not args.input:
        ap.error("review mode needs --input")

    problems = []
    (check_records if args.mode == "records" else check_review)(args, problems)
    for where, msg in problems:
        print(f"{where}\t{msg}")
    print(f"{len(problems)} problem(s)", file=sys.stderr)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
