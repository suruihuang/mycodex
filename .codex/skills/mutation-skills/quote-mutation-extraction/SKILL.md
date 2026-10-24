---
name: quote-mutation-extraction
description: Extract mechanism records (labels, evidence basis, verbatim evidence spans, functional effect) for rows of the mutation-quote dataset, and extract PDB IDs and decoded mutations from source papers when they are not supplied. Writes one JSON record per row. Not for reviewing records, copying the original dataset, or structure visualization.
---

# Quote mutation extraction

Read `../mutation-shared/rules.md` before starting. It defines the evidence scopes, mechanism labels, evidence basis, record fields, and interpretation rules. This skill says how to produce records; the rules say what a correct record contains.

## Inputs from the task

- The records to process: an input file and the IDs or row range.
- The evidence scope. If none is given, use `provided_data_only` and say so in your final message.
- Optionally, a numbering map of verified paper-to-PDB residue offsets (see the numbering rules).
- The output path. Never overwrite the input file or an earlier round's output.
- Optionally, a reflections file of general rules learned in earlier batches. Apply them as guidance; they are not answers for specific IDs.
- In a revision round, the review file (see Revision).

## Independence

Do not read mechanism labels, verdicts, or outputs from earlier runs for these IDs, existing mechanism columns in the data, or another agent's answers. The only exceptions are the reflections file and, when revising, the current review file and your own previous round.

## Procedure for each record

Work through these questions, then write the record. The answers are working notes; only the record fields are output.

1. What substitution is specified, and which protein, chain, and residue does it affect?
2. What interaction or structural feature does the quote describe? Does it concern the mutated residue?
3. How could the substitution change that interaction or feature?
4. Which mechanism label and evidence basis does the evidence in scope support? Keep the mutation's effect distinct from the wild-type interaction.
5. Which exact quote text does it rest on?
6. Does the evidence establish an effect on binding or activity, and for which measurement? If not, "Not established".
7. Are there inconsistencies or missing information in the supplied fields? Record them in `input_flags` rather than correcting the fields.

Batch runs are unattended: do not stop to ask for sources. When the evidence in scope is insufficient, use `not_assessable` or "Unverified", and say in `uncertainty` which source would resolve it.

## Output and validation

Write one JSON record per line to the output path. Then run

    python3 ../mutation-shared/validate.py records <output.jsonl> --input <input.csv>

and fix every reported problem before finishing. Add `--id-col` or `--quote-col` if the input uses other column names. Without an input file (paper mode), omit `--input`.

## Revision

When given a review file, respond to every issue on every record marked `revise`:

- Accept, partially accept, or decline each issue, with a brief evidence-based reason.
- Do not change an answer only to agree with the reviewer. A declined issue with a good reason is a valid outcome.
- Write revised records, only for the records under revision, to the new output path given by the task.
- Write a revision log with one JSON object per record: `ID`, `round`, `responses` (one per issue, in order: `issue_index`, `decision` of accept, partial, or decline, and `reason`), and `changes` (each changed field with `before` and `after`).
- Validate the revised records as above.

## Paper mode

When PDB, decoded mutation, or citation is not supplied and the user provides a quote with a paper (PDF path, text, DOI, or URL) or a structure file, extract those fields too, under `paper_assisted` or `structure_assisted` scope, following the rules on PDB verification, numbering, and constructs. In an interactive session, ask for the source paper or relevant sections when the quote does not identify the protein, structure, or mutation; in a terminal, accept a local PDF path and do not assume attachment controls exist. Use whatever tools are available: PyMuPDF for PDF text with page references, requests for database records, Biopython for PDB/mmCIF files. Use OCR only when needed, and review uncertain recognition results.

## Excel export

When the task asks for a workbook, convert validated records to .xlsx with openpyxl: supplied fields first, in input order, then the added fields, with lists joined by "; ". Write every value as a literal string, never a formula (values starting with "=" included), with wrapped text, readable column widths, a frozen header, and filters. Report the saved path. If a workbook cannot be created, write a TSV with the same columns and say that no workbook was created.
