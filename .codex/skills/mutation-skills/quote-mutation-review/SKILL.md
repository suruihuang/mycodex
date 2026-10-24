---
name: quote-mutation-review
description: Read-only review of quote-mutation-extraction records against the shared mutation rules - mechanism labels and taxonomy level, evidence basis, evidence spans, mutation versus wild-type effects, functional effects, and input flags. Returns a verdict and typed issues per record. Never edits records.
---

# Quote mutation review

Read `../mutation-shared/rules.md` first. Judge each record against those rules and against the evidence allowed by its `evidence_scope`, and nothing else.

## Inputs from the task

- The records file to review, the input file with the supplied fields, and the numbering map when the task supplies one.
- In a re-review round, the extractor's revision log and the IDs to re-review.
- The output paths for verdicts and for proposed rules.

Do not read the reflections file, the extractor's working notes, or outputs and verdicts from earlier runs. You review against the fixed rules; reflections are guidance for the extractor only.

You never edit records. Your output is verdicts and issues.

## What to check

Review every record in the batch, not only doubtful ones.

1. Does the mechanism explain the specified substitution, or only describe the wild-type interaction?
2. Are the labels correct and at the right level of the taxonomy?
3. Is the evidence basis right? An inference labeled `explicit_reported`, or a reported mechanism labeled `not_assessable`, is an error.
4. Is every material claim supported by the evidence in scope and appropriately qualified? Do the evidence spans support the mechanism?
5. Are residue mapping, wild-type contacts, and mutation effects kept apart correctly?
6. Is the functional effect specific to this mutation, with measurements kept distinct and group results not divided among component mutations?
7. Are problems in the supplied fields flagged in `input_flags`?
8. Did the record stay within its evidence scope?

Out of scope: whether the paper's findings are true, energetics or ΔΔG unless the record itself makes such a claim, and wording style.

Before calling a claim unsupported or a mechanism missed, search the quote and supplied fields for it. Every issue cites verbatim text from the supplied fields. For an unsupported claim, cite the passage the claim relies on and say what it does not establish.

## Verdicts

- `accept`: no material issue. Minor wording does not justify `revise`.
- `revise`: at least one issue with a specific correction.
- `needs_human`: the record cannot be settled within its scope, for example damaged OCR, or a disagreement that the evidence does not resolve.

## Error types

- `wrong_label`: the label does not match the evidence.
- `wrong_taxonomy_level`: right family, wrong level, for example a salt bridge labeled `hydrogen_bonding`.
- `wt_not_mutation`: describes the wild-type interaction without the substitution's effect, or labels an interaction the substitution preserves.
- `wrong_basis`: evidence basis misclassified.
- `missed_inference`: `not_assessable` where residue chemistry in scope supports a mechanism.
- `over_inference`: a mechanism the evidence in scope does not support.
- `unsupported_claim`: a contact, mapping, energetic, or functional claim without support.
- `residue_mapping`: wrong protein, chain, residue, or numbering, or the quote concerns a different residue.
- `effect_error`: measurements conflated, an effect stated without data, or a group result attributed to one mutation.
- `missed_input_flag`: a problem in the supplied fields left unflagged.
- `scope_violation`: evidence used outside the record's scope.

## Output

One JSON object per record, one per line:

    {"ID": "6", "verdict": "revise", "issues": [{"error_type": "wrong_basis", "field": "evidence_basis", "issue": "...", "cite": "<verbatim text from supplied fields>", "suggested_correction": "..."}]}

`issues` is empty for `accept`. Raise as many issues as the record has; there is no quota. Then run

    python3 ../mutation-shared/validate.py review <review.jsonl> --input <input.csv>

and fix every reported problem.

## Re-review

Re-review only the listed IDs, reading the extractor's response to each issue. If the extractor declined an issue with an evidence-based reason, either accept the record or mark it `needs_human` with both positions stated; do not repeat the same issue without new evidence. Justified disagreement may stand.

## Proposed rules

After each batch, write at most three general rules to the proposed-rules path, each with the error type it addresses and the IDs where it occurred. A rule must apply to records beyond this batch. Never phrase an answer for a specific ID as a rule.
