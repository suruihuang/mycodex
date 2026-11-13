# MutMech

Labels the molecular mechanism by which a mutation in a protein complex changes binding, from a literature
quote or a paper PDF, and explains the label. A command-line demo: there is no graphical interface.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt     # no pip in the venv: <other pip> --python .venv/bin/python install -r requirements.txt
cp config.example.toml config.toml            # then set the paths and the Codex binary
.venv/bin/python -m mutmech reproduce         # checks against the logged numbers, no LLM calls
```

`config.toml`, `runs/` and PDFs are not committed: they point at or hold private data.

## Analyse one mutation or a small batch

```bash
.venv/bin/python -m mutmech analyze --mutation "D364A (chain B)" --pdb 1A22 --quote "hGH Arg64 interacts with Asp164 ..."
.venv/bin/python -m mutmech analyze --mutation "D364A (chain B)" --pdb 1A22 --pdf paper.pdf --rule stmt
.venv/bin/python -m mutmech analyze --batch rows.csv --rule routing
```

Rules (`--rule`):

| Rule | What it does | LLM calls |
| --- | --- | --- |
| `routing` (default) | Evidence routing v0 with no-hint quotes decided by the single agent, the best method on the first-500 benchmark. One mechanism keyword in the quote gives that class. Several keywords: the PDB contacts pick the primary when they confirm exactly one, else the single agent picks among them. No keyword: the single agent's labels. | 0 or 1 |
| `baseline` | The single-agent baseline skill (`skills/baseline/SKILL.md`). | 1 |
| `v4` | Rules v4, extractor only (`skills/v4`), with its validator. | 1 |
| `stmt` | Statement rules (`skills/stmt/rules.md`): the quote is split into statements, each statement is classed for this mutation as causal, proposed causal, relationship or context, and the record gets a class. | 1 |

- The mutation is in PDB numbering. For a PDF, the residue is searched under its PDB number and under the paper
  numbers the numbering map gives for that entry and chain; pass `--paper-number` when the map has none.
- Output in `runs/analyze/<time>-<PDB>-<mutation>/result.json`: the labels (primary first), a description and an
  explanation, the PDF passages used, and per rule the route, keyword classes and structure contacts (`routing`),
  the evidence basis and uncertainty (`v4`), or the statements with their class and the record class (`stmt`).
  `--json` prints the whole record; `--dry-run` writes the prompt and stops before any LLM call.
- A batch CSV has the columns `mutation`, `pdb`, and `quote` or `pdf`, optionally `citation` and `paper_number`.
  Each row gets its own result folder under `runs/analyze/batch-<time>/`, which also holds `summary.csv`.
  Rows run one after another, one Codex call per row at most.
- Recorded for every call: the model Codex actually used, its reasoning effort, sandbox, network setting and
  approval policy (read from Codex's own session file), token use, and the SHA-256 of the skill files and the prompt.
- Text from a PDF comes from its text layer; scanned PDFs need OCR first, which this tool does not do.

## Find mutations in a paper

```bash
.venv/bin/python -m mutmech analyze --pdf paper.pdf --pdb 1A22 --list-mutations          # no LLM call
.venv/bin/python -m mutmech analyze --pdf paper.pdf --pdb 1A22 --mutations "R43A,D164A" --rule stmt
```

- `mutmech/findmut.py` reads the text layer for R64A, Arg64Ala, Arg-64-Ala, Arg64→Ala, "Arg64 to alanine",
  "mutation of Arg64 to Ala" and single alanine substitutions ("alanine substitution of Arg64"). Figure labels
  such as "Fig. S1A" and dipeptides such as "Gln49-Thr50" are skipped.
- Hits are grouped by wild type, paper number and mutant, with count, pages, forms as written and up to three
  context sentences. With `--pdb`, each is placed on a chain with the numbering map's offset (0 where the map has
  none) and its wild type is checked against the cached structure: matches, mismatch or not checked. Structure
  matches rank first, then by count.
- `--mutations` takes names as written in the paper or in PDB numbering and runs them as a batch with the PDF as
  evidence. A residue the paper only names, without stating a substitution, is not listed.
- Without `--pdb`, `mutmech/pdbguess.py` proposes the entry, with no LLM call and no network: IDs written near
  PDB, accession, code, entry, coordinates or deposited; the PDF's file name in the input CSV's Citation column or
  as a prefix that names a known entry (the dataset's own table and naming); and cached structures whose mmCIF
  title and entity names the paper's first page largely covers. Candidates are ranked by how many of the paper's
  wild types match the structure (numbering-map offsets, plus a per-chain offset inferred when one clearly fits),
  then by number of sources. The best is used; `--list-mutations` prints the list first. No RCSB search: this
  repository makes no network fetches.
- In the GUI this is the Paper view: upload, the PDB entry is proposed and can be switched from a list or typed,
  pick rows (PDB mutation and chain are editable), choose a rule.
- When a Codex call reports its usage limit, the GUI shows "Codex usage limit reached, retry after <time>" on that
  row or result and pauses its queue until then; a paused batch runs the row again. The command line stops the
  batch at that row.

## Web GUI

```bash
.venv/bin/python -m mutmech serve [--port 8765]     # then open http://127.0.0.1:8765/
```

- Listens on 127.0.0.1 only and answers only to a 127.0.0.1 or localhost Host header, because inputs and
  results are private. Standard library only; the page (`mutmech/web/`) loads nothing from the network.
- Analyze: mutation, PDB entry, optional citation and paper number, a quote or an uploaded PDF (saved under
  `runs/uploads/`), the rule and a dry-run switch. It calls the same `analyze` code as the command line.
- Jobs run on one worker thread, so Codex calls never run in parallel. The page polls for queued, running, done
  or error and shows elapsed time.
- Result: the primary label and all labels, description and explanation, the rule's panel (route, keyword
  classes and structure contacts; statements with their classes; or the v4 evidence basis and uncertainty), the
  quote or PDF passages with the residue highlighted, provenance (model, sandbox, network, tokens, hashes, run
  folder), and the prompt for a dry run. `/?result=<run folder below runs/analyze>` opens one result directly.
- Batch: upload a CSV in the `--batch` format; the table fills row by row and links each row to its result.
  `pdf` cells are paths on this machine.
- History: every `runs/analyze/**/result.json`, newest first; click a row to open it.
- Scanned PDFs still need OCR first.

## Structure view

The Result view and each row of the Paper view (button "Structure", no LLM call) show the mutation site on the
cached structure: cartoons coloured by chain with a legend naming each chain's protein from the numbering map, the
mutated residue as sticks labelled like `B:D364 (paper D164) → A`, residues within 4.5 Å as thin sticks with
partner-chain residues listed beside the viewer with their contact types (the routing code's structure contacts),
and residues the statement-rules analysis names as participants. Controls: focus on site, whole structure, labels,
surface, save PNG. It is a site annotation on the deposited structure; the mutant side chain is not modelled. A
wild type that does not match the structure (1A22 carries Arg120, so hGH G120R) is shown as a mismatch with no
neighbours. `GET /api/structure?pdb=1A22` serves the cached mmCIF (`&format=pdb` gives the first model the viewer
draws); a missing entry gives an error, and nothing is fetched from the network. Needs WebGL.

The viewer is 3Dmol.js 2.5.3, vendored in `mutmech/web/vendor/` with its licenses, from
https://cdn.jsdelivr.net/npm/3dmol@2.5.3/build/3Dmol-min.js, SHA-256
`bcf422137a34b4e206413a8a83a67c24a1ace84e282bf3b164f6bda6aeb42a20` (checked by `mutmech reproduce`).

## Batch runs and scoring

```bash
.venv/bin/python -m mutmech pipeline run --dataset ids:FILE --methods baseline,v4-norev,stmt --name NAME   # see --help
.venv/bin/python -m mutmech score runs/pipeline/NAME stmt          # first-500 benchmark scoring
.venv/bin/python -m mutmech routing-v1 score dev --llm RUN_DIR
.venv/bin/python -m mutmech skempi-join
```

- `pipeline` methods: `baseline`; `v3`, `v4` (extractor, reviewer, revisions); `v3-nolessons`; `v3-norev`,
  `v4-norev` (extractor only); `stmt` (statement rules, extractor and validator, no reviewer).
- `score RUN_DIR METHOD` scores a finished or partial run on the records it has finished: the method, the
  baseline, the keyword rule, and the hybrid and routing methods built from either model's labels, with
  quote-clustered 95% intervals; for `stmt` also the statement structure. Answers, inputs and the baseline run
  come from `[first500]` in config.toml or `--answers`, `--inputs`, `--baseline-run`. Output in `runs/scores/`.
- The test set is scored once per frozen method (`--final`), with aggregates only.

## Reproduction checks

`mutmech reproduce` makes no LLM calls. It checks the keyword rule and routing v1 on dev, the SKEMPI join, the
first-500 answer file, and, when `[first500]` names the finished runs, the first-500 scores of the statement
rules, rules v4 extractor only, the baseline, the hybrid and routing with no-hint quotes by the LLM.

## Data and model provider

Every LLM call sends the quote or the PDF passages to the model behind Codex. Check that the data may go to
that provider before analysing private papers.

## Provenance

Copied on 2026-11-09 from the codex repository's `eval/` and `tools/` folders with path and import changes only:
`eval/pipeline/mutmech.py` (pipeline.py), `eval/routing/routing.py`, `eval/routing/routing_v1.py`,
`eval/skempi/join_skempi.py` (skempi.py), `eval/gold_workbook/score_gold.py` (gold.py), `tools/evaluate.py`,
the pipeline prompts and the baseline skill. The prompts now take the list of folders the LLM must not open from
the config, so their independence line differs from earlier runs; nothing else in them changed.
Added on 2026-11-11: the statement rules (`skills/stmt`, unchanged from `eval/skills_stmt`, and
`prompts/stmt/extract.md` with the same independence change), the four rules-v4 skill files (`skills/v4`,
unchanged from `eval/skills_v4`), and `score.py`, ported from `eval/first500/score_vs_baseline.py` and
`score_stmt.py`. `python -m mutmech reproduce` checks the result.
Changed on 2026-11-13: the last machine paths in the prompts, the source workbook's folder and the rules-v4 folder,
became `{{WORKBOOK_DIR}}` and `{{V4}}`, filled from `curator_workbook` and `skills_v4` in the config. With the
original config the filled baseline, v4 and statement-rules prompts are byte-identical to before; the v3 prompts now
name the configured v4 folder instead of `eval/skills_v4`.
