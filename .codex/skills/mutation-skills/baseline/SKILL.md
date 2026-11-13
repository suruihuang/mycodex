---
name: quote-mechanism-baseline
description: Single-agent baseline for the mutation-quote dataset. Reads each row's ID, PDB, Mutation DECODED, Quote, and Citation and writes one mechanism record per ID. Use only when a task asks for the baseline run; not for the rules-based extraction or review pipeline, PDB verification, or structure visualization.
---

# Quote mechanism baseline

For each requested row, state which molecular interaction the mutation changes. This is a baseline: one agent, the supplied fields as the only evidence, no shared rules file, no validator, no review round.

## Inputs from the task

- The input CSV, read-only, with columns `ID`, `PDB`, `Mutation DECODED`, `Quote`, `Citation`, and the IDs to process.
- Optionally, a numbering map of paper-to-PDB residue offsets.
- The output path. Never overwrite the input file.

Batch runs are unattended: do not ask for papers or other sources, and do not fetch any. Work from the supplied fields only.

## Independence

Do not read mechanism labels or outputs from other runs, mechanism columns in the source data, or another agent's answers.

## Mutation and mechanism interpretation

- Decode the supplied mutation with the affected protein, chain, original amino acid, residue number, and replacement. Example: 1A22 `D364A (chain B)` — growth hormone receptor Asp364 → Ala.
- `Mutation DECODED` uses the structure's numbering; the quote may use the paper's (1A22 receptor Asp364 is Asp164 in the paper). Match the two with the numbering map when one is supplied, otherwise by amino acid and context. Say in `reason` when the match is uncertain or the quote does not mention the residue.
- Residue contacts alone do not specify a mutation. For "R64 interacts with D164 and E44", record the interaction partners without inventing substitutions.
- Distinguish the mutation in the crystallized construct from mutations tested in functional experiments.
- Connect molecular interactions to reported behavior where supported. Distinguish experimental observations, author-proposed mechanisms, and additional inferences explicitly.
- Keep association rate, dissociation rate, equilibrium affinity, and signaling activity distinct. Do not invent individual values from a grouped result or infer one measurement from another without sufficient data.
- Flag ambiguous OCR in the quote, especially residue identities and measurements, in `reason`. Do not correct the quote.
- Every record needs a mechanism. When the quote names no interaction for the residue, give the most likely one from the residue's chemistry and say in `mechanism` that it is an inference. Never invent a contact, a partner, or a measurement.

## Mechanism labels

Use one or more of these labels, primary first:

| Label | Covers |
| --- | --- |
| `electrostatic` | Salt bridges, ionic or charge–charge interactions, electrostatic steering |
| `hydrogen_bonding` | Hydrogen bonds |
| `hydrophobic` | Van der Waals contacts, nonpolar packing or burial |
| `aromatic` | π–π stacking, cation–π, CH–π interactions |
| `steric` | Clashes, loss of shape complementarity |
| `conformational` | Backbone flexibility, secondary-structure, loop or domain changes, allosteric effects |
| `covalent_or_metal` | Disulfide bonds, metal coordination |
| `other` | Anything else; name it in `mechanism` |

## Output

Write one JSON object per line to the output path, one per requested ID, in the order given:

```json
{"ID": "<ID>", "mechanism_labels": ["<primary label>", "<other label>"], "mechanism": "...", "reason": "..."}
```

- **ID:** As in the input.
- **mechanism_labels:** Labels from the table, primary first; never empty.
- **mechanism:** Concise supported mechanism and relevant observed effect, identifying hypotheses or inferences.
- **reason:** The evidence connecting the mutation, the quote, and the mechanism, including construct differences and remaining uncertainty.

Before finishing, check that every requested ID appears exactly once and every label is from the table. Report the output path and the number of records written.
