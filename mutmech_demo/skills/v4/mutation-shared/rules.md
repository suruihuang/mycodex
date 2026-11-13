# Mutation mechanism rules

Version 4, curator standard (draft, 2026-10-21). Labels follow the curators' convention in the source workbook, and every record gets a mechanism.

Shared by the quote-mutation-extraction and quote-mutation-review skills. `validate.py` in this folder reads the backticked codes in the first column of the Evidence scope, Mechanism labels, and Evidence basis tables, so add or rename codes only in those tables.

## Evidence scope

The task names one scope. Record it in every record's `evidence_scope`.

| Scope | Allowed evidence |
| --- | --- |
| `provided_data_only` | This record's supplied fields, the numbering map when the task supplies one, and general biochemical knowledge (residue charge, polarity, size, aromaticity). Other records, the paper, and the structure are out of scope. |
| `structure_assisted` | The above plus the supplied PDB structure. Verify chain, residue numbering, and construct identity before using it, and record the chains, residues, and observations used. If the structure cannot be inspected or mapped reliably, say so in `uncertainty` and do not use `structure_inference`. |
| `paper_assisted` | The above plus the source paper, supplied as text or reachable by path, DOI, or URL. Cite page, section, table, or figure for each excerpt used. Disclose sources that could not be accessed. |

## Mechanism labels

`mechanism_labels` is a list of these codes, primary first, and is never empty. Labels follow the curators' convention: they name the interactions the mutated residue makes in the evidence, including backbone contacts and interactions the substitution may keep (for example the alkyl packing of Arg43, also for R43L). List every interaction type the evidence names for the residue. The `mechanism` sentence says how the substitution is expected to change them. Subtypes (salt bridge, π–π stacking) are named in the `mechanism` sentence, not as labels.

| Label | Covers | Not this label when |
| --- | --- | --- |
| `electrostatic` | Salt bridges, ionic interactions, charge–charge attraction or repulsion, long-range electrostatic steering, effects the evidence attributes to charged residues as a class | The evidence names only hydrogen bonds, even between charged side chains: use `hydrogen_bonding`, and add `electrostatic` only when a salt bridge or ionic interaction is also named |
| `hydrogen_bonding` | Any hydrogen bond named for the residue: side chain or backbone, direct or water-mediated, between oppositely charged side chains, or within a named group or network the residue belongs to | The evidence names only a salt bridge or ionic interaction: use `electrostatic` |
| `hydrophobic` | Van der Waals contacts, burial or contact of nonpolar side chains, nonpolar packing, cavities left by removing a nonpolar side chain | A larger side chain no longer fits: use `steric` |
| `aromatic` | π–π stacking, cation–π, and CH–π interactions of aromatic rings | |
| `steric` | Clashes from a larger side chain, loss of shape complementarity | |
| `conformational` | Backbone flexibility (Pro, Gly), secondary-structure destabilization, loop or domain rearrangement, allosteric effects | |
| `covalent_or_metal` | Disulfide bonds, metal coordination | |
| `other` | A mechanism not covered above; name it in `mechanism` | |

## Evidence basis

One basis per record, for the primary label.

| Basis | Meaning |
| --- | --- |
| `explicit_reported` | The evidence reports the mechanism as an observation or measurement ("forms a salt bridge with", "the hydrogen bond is lost in the mutant", "these residues form only van der Waals contacts"). Mapping a named interaction to its label (van der Waals contact → `hydrophobic`, salt bridge → `electrostatic`) is still `explicit_reported`. |
| `author_proposed` | The authors offer the mechanism as interpretation or with hedging ("may", "likely", "we propose"). |
| `structure_inference` | Inferred from inspected coordinates. Only under `structure_assisted`. |
| `chemical_inference` | Inferred from residue chemistry when the allowed evidence names the residues or contact but not the interaction type, or attributes an effect to a class of residues. Example: "Arg64 interacts with Asp164 and Glu44" reports a contact; `electrostatic` is then a chemical inference, not a reported mechanism. |
| `weak_inference` | No interaction is named for this residue: the evidence is an effect only, a curator note, a contact without partner or type, or it concerns another substitution or residue. Give the most likely interaction from the residue's chemistry and the context, and say in `uncertainty` what would confirm it. Use it instead of leaving a record without a mechanism. |

## Record fields

One JSON object per record, one record per line (JSONL).

Supplied fields: every column of the input row, under its original name, copied verbatim, blanks included. In the standard dataset these are `ID`, `PDB`, `Mutation DECODED`, `Quote`, and `Citation`. When PDB, mutation, or citation is not supplied and the task asks for them, fill them by the rules below, with "Not stated" for absent information and "Unverified" for unresolved assignments.

Added fields:

- `evidence_scope`: the scope code.
- `mechanism_labels`: list of label codes.
- `mechanism`: one or two sentences naming the interaction the residue makes and how the substitution is expected to change it, keeping the wild-type interaction distinct from the mutation's effect.
- `evidence_basis`: the basis code.
- `evidence_spans`: list of exact substrings of `Quote` that the mechanism rests on, copied character for character, OCR errors included. Empty only with `weak_inference` when the quote holds no text about the residue.
- `supporting_evidence`: what connects the evidence to the mechanism. Name residues and partners. For structure or paper evidence, give chain, residue, and observation, or page, section, or figure with the excerpt, labeled by source.
- `functional_effect`: the measured effect of this mutation, naming the measurement (association rate, dissociation rate, equilibrium affinity, signaling activity), or "Not established".
- `uncertainty`: what remains unresolved and which source would resolve it, or "None".
- `input_flags`: list of problems found in the supplied fields, empty if none. Suggested codes: `contact_only` (the quote describes contacts, not a substitution), `mutation_not_in_quote`, `mutation_mismatch` (the supplied mutation disagrees with the quote), `group_construct`, `numbering_mismatch`, `ocr_suspect`, `pdb_unverified`.

## Interpretation rules

Mutations
- Decode each substitution as protein, original residue, number, and replacement. Example: hGH R64A is human growth hormone Arg64 → Ala.
- Residue contacts alone do not specify a mutation. For "R64 interacts with D164 and E44", record the interaction partners and do not invent substitutions.
- One record per individually tested mutation. A jointly tested multiple-mutant construct stays one record; do not divide its measured effect among its component mutations.
- Distinguish the mutation in the crystallized construct from mutations tested in functional experiments. A structural template is not the experimentally determined structure of every mutant.

Mechanisms
- The quote often describes the wild-type interaction. Label that interaction, as the curators do, and say in `mechanism` how the substitution is expected to change it.
- Every record gets a mechanism. When the evidence is thin, give the most likely label with `weak_inference` and state what would confirm it.
- Hydrogen bonds: label `hydrogen_bonding` whenever the evidence says the residue forms hydrogen bonds, alone, as one of a named group of residues, or within a named hydrogen-bond network, whether its side chain or backbone takes part.
- Charged residues as a class: when the evidence attributes an effect to charged residues (for example on-rate changes found only for charged substitutions), label `electrostatic` as `chemical_inference`.
- Contacts without a type: choose by the residue's chemistry. Nonpolar side chains get `hydrophobic`, aromatic rings get `aromatic` only when stacking or a π interaction is named, polar neutral side chains get `hydrogen_bonding`, and charged side chains get `electrostatic`.
- Supplied mutation differs from the quote: when the quote describes another substitution at the same residue, label the interaction the quote gives for that residue, flag `mutation_mismatch`, and say so in `uncertainty`.
- Keep experimental observations, author-proposed mechanisms, and inferences apart, and record which one applies through `evidence_basis`.
- Do not invent residue mappings, contacts, or energetic effects. A weak label is allowed; an invented contact or measurement is not.
- Keep association rate, dissociation rate, equilibrium affinity, and signaling activity distinct. Do not infer one measurement from another, or individual values from a grouped result.

Structures and numbering
- A PDB identifier is not inspected structural evidence. Use structure evidence only under `structure_assisted`, after inspecting the coordinates.
- Verify PDB identifiers from a deposition statement or an authoritative PDB record linked to the paper. Never assign one from a filename, title, or residue numbers alone.
- Distinguish structures deposited by the paper from structures cited for comparison. A functional mutant need not have its own deposited structure.
- Preserve paper numbering. Assign chains and PDB residue numbers only after verifying the mapping, including insertion codes, missing residues, and numbering offsets. Verify offsets per entry; never carry one entry's offset to another.
- A numbering map supplied with the task counts as verified for the entries and chains it lists. Use it to match supplied PDB numbering to the paper numbering in the quote, name the mapping in `supporting_evidence` (for example "1A22 chain B: PDB 364 = paper 164"), and do not flag `numbering_mismatch` for residues it resolves. For entries and chains it does not list, the rule above applies.
- When the supplied mutation and the quote name the same amino acid at the same residue number, treat that residue's mapping as verified by identity and say so in `supporting_evidence`.
- When numbering cannot be verified, still label from the supplied residue and the quote with `weak_inference`, and flag `numbering_mismatch`.

Supplied data
- Never modify supplied fields. Record inconsistencies in `input_flags` and explain them in `uncertainty`.
- Flag ambiguous OCR, especially residue identities, accession codes, and measurements. Do not silently correct it; explain any normalization an assignment depends on.
- When OCR damage leaves the clause naming the residues and their interaction readable, extract from it normally and add `ocr_suspect`. When the damage falls on a residue identity and the supplied mutation resolves it to one reading, use that reading and state it in `uncertainty`. Otherwise label with `weak_inference`.
- Cite only sources actually inspected.
