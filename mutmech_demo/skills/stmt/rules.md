# Statement rules for mutation mechanism records

Draft 1, 2026-11-10. Each record pairs one substitution with one quote. A quote can hold several statements, and a statement can describe a relationship without making a causal claim about the substitution. Records are therefore built in two layers:

1. **Quote layer.** Split the quote into statements and describe each one. This depends only on the quote, so every record that shares a quote gets the same statements.
2. **Record layer.** For this record's substitution, judge how each statement relates to it. The statement classes, the record class and the labels follow from those judgments by fixed rules.

`validate.py` reads the backticked codes in the first column of each code table below, so add or rename codes only in those tables.

## Allowed evidence

The record's supplied fields, the numbering map when the task supplies one, and general biochemical knowledge of residue chemistry (charge, polarity, size, aromaticity, which atoms a substitution keeps). Not the paper, not the structure, not other records' labels.

## Quote layer

### What a statement is

A statement is one claim: an observed interaction or arrangement, a measured result, an interpretation, a claim credited to earlier work, or context.

- Split a sentence that holds claims of different kinds. "Asn33 hydrogen-bonds the carbonyl of Thr17, which would oppose the movement of Leu18" is two statements: an observation and an interpretation. "R64A binds 100-fold more weakly, which we attribute to loss of the salt bridge" is two statements: a measurement and an interpretation.
- Do not split one claim by partner. "Asn33 hydrogen-bonds the carbonyl oxygens of Thr17 and Glu19" is one statement with three participants.
- Tables: the caption or heading is a `context` statement. Each row naming a contact pair is a `structure_observation` whose interaction type comes from the caption or column heading. Adjacent rows about the same residue pair may form one statement.
- `span` is an exact substring of `Quote`, OCR errors included. A span may be part of a sentence. Spans appear in quote order and do not overlap.
- Every claim about residues, interactions, structures, measurements or mechanisms must be in a statement. Text with no claim, such as reference numbers or garbled fragments, may be left out.
- At most 15 statements per quote. When a quote holds more claims, merge adjacent claims of the same kind about the same residues.
- Write statements from the quote alone. Do not let the record's mutation change how the quote is split or described. Records with the same `Quote` must carry identical `statements`.
- The number of statements is used downstream to separate single-statement from multi-statement quotes. Do not merge or split statements to change it.

### Statement kinds

| Kind | Meaning |
| --- | --- |
| `structure_observation` | An interaction, contact, distance or arrangement seen in a structure, including rows of contact tables |
| `measurement` | A measured quantity or experimental result: affinity, rate, activity, stability, ΔΔG, including results for mutants |
| `author_interpretation` | The authors' explanation, proposal or conclusion, hedged or not ("we attribute", "thus", "would", "may") |
| `prior_work` | A claim the quote credits to earlier work ("we have described previously", a citation) |
| `context` | Background, methods, captions or descriptions that make no claim about a specific interaction or result |

### Mechanism labels

`interactions` lists the interaction types the statement names, using these codes. A statement with no interaction has an empty list.

| Label | Covers | Not this label when |
| --- | --- | --- |
| `electrostatic` | Salt bridges, ionic interactions, charge–charge attraction or repulsion, electrostatic steering, effects attributed to charged residues as a class | Only hydrogen bonds are named, even between charged side chains: use `hydrogen_bonding` |
| `hydrogen_bonding` | Any named hydrogen bond: side chain or backbone, direct or water-mediated, between charged side chains, or within a named network | Only a salt bridge or ionic interaction is named |
| `hydrophobic` | Van der Waals contacts, burial or packing of nonpolar side chains, cavities left by removing a nonpolar side chain | A larger side chain no longer fits: use `steric` |
| `aromatic` | π–π stacking, cation–π and CH–π interactions of aromatic rings | |
| `steric` | Clashes from a larger side chain, loss of shape complementarity | |
| `conformational` | Backbone flexibility, movements, loop or domain rearrangement, secondary-structure changes, allosteric effects, a structural element anchoring another | |
| `covalent_or_metal` | Disulfide bonds, metal coordination | |
| `other` | A mechanism not covered above; name it in `rationale` | |

### Interaction source

| Source | Meaning |
| --- | --- |
| `named` | The statement names the interaction type or a term that maps to one (salt bridge, van der Waals contact, H bond, stacking, clash, movement), including a type given by a table caption |
| `chemistry` | The statement names a contact without a type. Choose by chemistry: nonpolar side chains `hydrophobic`, polar neutral `hydrogen_bonding`, charged `electrostatic`, aromatic rings `aromatic` only when stacking or a π interaction is named |
| `none` | `interactions` is empty |

### Participants

`participants` lists the residues or groups the statement names, each as `{"residue": "Thr17", "chain": "I", "part": "backbone"}`. Use the three-letter code and the number as written in the quote. Normalize OCR only when the reading is clear ("Asn-331" in an inhibitor-chain context read as Asn33, chain I) and add `ocr_suspect` to the record's `input_flags`. Use an empty `chain` when neither the quote nor the numbering map gives one. Waters, metals and ligands are participants with their name as `residue` and part `unspecified`.

| Part | Meaning |
| --- | --- |
| `side_chain` | The side chain, or a side-chain atom (OG1, NZ, the amide of Asn) |
| `backbone` | Main-chain atoms only (N, NH, CA, C, O, "carbonyl oxygen", "main-chain NH") |
| `unspecified` | The residue is named without saying which part takes part |

### Effect

| Effect | Meaning |
| --- | --- |
| `mutation_effect` | Reports or explains an effect of a named substitution or group of substitutions: binding, rate, activity, stability, or a structural change in the mutant |
| `wild_type_function` | States or proposes what a wild-type residue, interaction or structural element does: contributes to binding, anchors, opposes a movement, determines specificity |
| `none` | Describes without any effect or function |

`effect_of` lists, as written, the substitutions, groups, residues or elements whose effect or function the statement gives ("R64A", "charged substitutions at P1", "Thr66"). It is empty exactly when `effect` is `none`.

### Certainty

| Certainty | Meaning |
| --- | --- |
| `asserted` | Stated as fact: observations, measurements and unhedged conclusions ("we attribute", "is due to", "thus") |
| `hedged` | Qualified: may, might, could, would, likely, possibly, presumably, suggest, propose, appear to, consistent with |

## Record layer

For each statement, one entry in `links` with the same `sid`.

### Relation to the substitution

| Relation | Meaning |
| --- | --- |
| `side_chain` | A participant is the mutated residue with part `side_chain` |
| `backbone` | The mutated residue takes part only through backbone atoms |
| `residue_unspecified` | The mutated residue is named without a part, the statement is a result for its substitution, or the quote is a short note evidently about this record's residue that names no residue |
| `partner` | The mutated residue is not named, but the statement concerns a residue the quote shows interacting with it, or a group, network or element the quote places it in |
| `unrelated` | None of the above |

### After the substitution

Judged for the statement's interaction, from the replacement residue's chemistry or from what the quote reports for the mutant. Only for relations `side_chain`, `backbone` and `residue_unspecified` with a non-empty `interactions`. Every other entry is `not_applicable`.

| After | Meaning |
| --- | --- |
| `lost` | The replacement cannot make this interaction (Arg→Ala salt bridge, Thr→Ala hydroxyl hydrogen bond, Leu→Asp nonpolar packing), or the quote reports it lost in the mutant |
| `changed` | The replacement makes a weaker or altered version (Arg→Lys salt bridge, Leu→Ala packing, Asp→Glu), adds a clash, or changes backbone flexibility (to or from Pro or Gly) |
| `kept` | Atoms the substitution keeps make the interaction: the backbone carbonyl always, the backbone NH unless the replacement is Pro; or the quote reports it kept |
| `unclear` | Cannot be judged from the chemistry and the quote |
| `not_applicable` | See above |

### Applies to

| Applies | Meaning |
| --- | --- |
| `this_mutation` | `effect` is `mutation_effect` and `effect_of` covers this record's substitution: the same substitution, substitutions at this residue as a group, or a named group it belongs to |
| `other_mutation` | `effect` is `mutation_effect` and concerns only other substitutions |
| `wild_type` | `effect` is `wild_type_function` |
| `none` | `effect` is `none` |

### Statement classes

Each statement's class follows from the fields above by the first rule that matches. Write the class that the rules give.

| Class | Rule |
| --- | --- |
| `context` | Relation `unrelated`, or `interactions` empty and applies not `this_mutation` |
| `effect_only` | `interactions` empty and applies `this_mutation`: the substitution's effect without a mechanism |
| `causal` | Relation `side_chain`, `backbone` or `residue_unspecified`, after `lost` or `changed`, applies `this_mutation`, certainty `asserted` |
| `proposed_causal` | Relation `side_chain`, `backbone` or `residue_unspecified`, after `lost` or `changed`, and either applies `this_mutation` with certainty `hedged`, or applies `wild_type` |
| `relationship` | Every other statement: an interaction of the site without a link to an effect, one the substitution keeps, one about a partner, or one tied to another substitution |

### Record classes

| Record class | Rule |
| --- | --- |
| `causal` | At least one `causal` statement |
| `proposed_causal` | No `causal` statement, at least one `proposed_causal` |
| `relationship_only` | No causal or proposed statement, at least one `relationship` |
| `no_mechanism_statement` | Only `effect_only` and `context` statements |

### Labels

- `mechanism_labels`: the interactions of `causal` statements, then of `proposed_causal` statements, in statement order, without repeats. Empty when there are none.
- `context_labels`: the interactions of `relationship` statements, those with relation `side_chain`, `backbone` or `residue_unspecified` first, then `partner`, in statement order, without repeats.
- `inferred_labels`: only when both lists above are empty, the most likely interaction from the residue's chemistry and the quote, primary first. This is a weak inference, not a statement in the quote. Otherwise empty.

## Record fields

One JSON object per record, one per line (JSONL).

Supplied fields: every column of the input row under its original name, copied verbatim, blanks included (`ID`, `PDB`, `Mutation DECODED`, `Quote`, `Citation`).

Added fields:

- `statements`: list of `{sid, span, kind, interactions, interaction_source, participants, effect, effect_of, certainty}`, with `sid` S1, S2, … in quote order.
- `links`: list of `{sid, relation, after_substitution, applies, class}`, one per statement, same order.
- `record_class`, `mechanism_labels`, `context_labels`, `inferred_labels` as above.
- `functional_effect`: the effect of this substitution that the quote reports, naming the measurement (association rate, dissociation rate, equilibrium affinity, activity, stability), or "Not stated".
- `rationale`: one to three sentences naming the statement that decides the record class and why: which atoms the substitution keeps or removes, and whether the quote links the interaction to this substitution's effect.
- `input_flags`: problems in the supplied fields, empty if none. Suggested codes: `mutation_not_in_quote`, `mutation_mismatch`, `group_construct`, `numbering_mismatch`, `ocr_suspect`.

## Substitutions and numbering

- Decode each substitution as protein, original residue, number and replacement. A record that lists several substitutions at one residue is judged for the set; a jointly tested multiple mutant is judged as one construct and flagged `group_construct`.
- A numbering map supplied with the task counts as verified for the entries and chains it lists. When the supplied mutation and the quote name the same amino acid at the same number, treat that residue's mapping as verified by identity.
- When the supplied residue cannot be matched to the quote, judge the relation as `unrelated` unless the quote is evidently about it, and flag `numbering_mismatch` or `mutation_not_in_quote`.
- Never modify supplied fields. Never invent a contact, a partner or a measurement.

## Worked example

An invented quote: "Arg64 forms a salt bridge with Asp164 of the receptor, and its main-chain NH donates a hydrogen bond to Ser160. R64A binds 100-fold more weakly, which we attribute to the loss of this salt bridge. The Thr66 hydroxyl may help hold the loop in place by hydrogen bonding to the Gly62 carbonyl."

Quote layer, the same for every record with this quote:

| sid | span | kind | interactions | participants | effect, effect_of | certainty |
| --- | --- | --- | --- | --- | --- | --- |
| S1 | Arg64 forms a salt bridge with Asp164 of the receptor | structure_observation | electrostatic, named | Arg64 side_chain, Asp164 side_chain | none | asserted |
| S2 | its main-chain NH donates a hydrogen bond to Ser160 | structure_observation | hydrogen_bonding, named | Arg64 backbone, Ser160 unspecified | none | asserted |
| S3 | R64A binds 100-fold more weakly | measurement | none | Arg64 unspecified | mutation_effect, R64A | asserted |
| S4 | which we attribute to the loss of this salt bridge | author_interpretation | electrostatic, named | Arg64 side_chain, Asp164 side_chain | mutation_effect, R64A | asserted |
| S5 | The Thr66 hydroxyl may help hold the loop in place by hydrogen bonding to the Gly62 carbonyl | author_interpretation | hydrogen_bonding, named | Thr66 side_chain, Gly62 backbone | wild_type_function, Thr66 | hedged |

Record layer, as relation / after / applies → class:

| sid | Record R64A | Record R64K | Record T66A |
| --- | --- | --- | --- |
| S1 | side_chain / lost / none → relationship | side_chain / changed / none → relationship | unrelated → context |
| S2 | backbone / kept / none → relationship | backbone / kept / none → relationship | unrelated → context |
| S3 | residue_unspecified / not_applicable / this_mutation → effect_only | residue_unspecified / not_applicable / other_mutation → context | unrelated → context |
| S4 | side_chain / lost / this_mutation → causal | side_chain / changed / other_mutation → relationship | unrelated → context |
| S5 | unrelated → context | unrelated → context | side_chain / lost / wild_type → proposed_causal |
| Record class | causal | relationship_only | proposed_causal |
| mechanism_labels | electrostatic | – | hydrogen_bonding |
| context_labels | electrostatic, hydrogen_bonding | electrostatic, hydrogen_bonding | – |
| functional_effect | equilibrium affinity 100-fold weaker | Not stated | Not stated |

The R64A record as JSON, supplied fields shortened:

```json
{"ID": "...", "PDB": "...", "Mutation DECODED": "R64A", "Quote": "...", "Citation": "...",
 "statements": [
  {"sid": "S1", "span": "Arg64 forms a salt bridge with Asp164 of the receptor", "kind": "structure_observation", "interactions": ["electrostatic"], "interaction_source": "named", "participants": [{"residue": "Arg64", "chain": "", "part": "side_chain"}, {"residue": "Asp164", "chain": "", "part": "side_chain"}], "effect": "none", "effect_of": [], "certainty": "asserted"},
  {"sid": "S2", "span": "its main-chain NH donates a hydrogen bond to Ser160", "kind": "structure_observation", "interactions": ["hydrogen_bonding"], "interaction_source": "named", "participants": [{"residue": "Arg64", "chain": "", "part": "backbone"}, {"residue": "Ser160", "chain": "", "part": "unspecified"}], "effect": "none", "effect_of": [], "certainty": "asserted"},
  {"sid": "S3", "span": "R64A binds 100-fold more weakly", "kind": "measurement", "interactions": [], "interaction_source": "none", "participants": [{"residue": "Arg64", "chain": "", "part": "unspecified"}], "effect": "mutation_effect", "effect_of": ["R64A"], "certainty": "asserted"},
  {"sid": "S4", "span": "which we attribute to the loss of this salt bridge", "kind": "author_interpretation", "interactions": ["electrostatic"], "interaction_source": "named", "participants": [{"residue": "Arg64", "chain": "", "part": "side_chain"}, {"residue": "Asp164", "chain": "", "part": "side_chain"}], "effect": "mutation_effect", "effect_of": ["R64A"], "certainty": "asserted"},
  {"sid": "S5", "span": "The Thr66 hydroxyl may help hold the loop in place by hydrogen bonding to the Gly62 carbonyl", "kind": "author_interpretation", "interactions": ["hydrogen_bonding"], "interaction_source": "named", "participants": [{"residue": "Thr66", "chain": "", "part": "side_chain"}, {"residue": "Gly62", "chain": "", "part": "backbone"}], "effect": "wild_type_function", "effect_of": ["Thr66"], "certainty": "hedged"}],
 "links": [
  {"sid": "S1", "relation": "side_chain", "after_substitution": "lost", "applies": "none", "class": "relationship"},
  {"sid": "S2", "relation": "backbone", "after_substitution": "kept", "applies": "none", "class": "relationship"},
  {"sid": "S3", "relation": "residue_unspecified", "after_substitution": "not_applicable", "applies": "this_mutation", "class": "effect_only"},
  {"sid": "S4", "relation": "side_chain", "after_substitution": "lost", "applies": "this_mutation", "class": "causal"},
  {"sid": "S5", "relation": "unrelated", "after_substitution": "not_applicable", "applies": "wild_type", "class": "context"}],
 "record_class": "causal", "mechanism_labels": ["electrostatic"], "context_labels": ["electrostatic", "hydrogen_bonding"], "inferred_labels": [],
 "functional_effect": "Equilibrium affinity 100-fold weaker.",
 "rationale": "S4 attributes the weaker binding of R64A to loss of the Arg64–Asp164 salt bridge, which alanine cannot make. The backbone hydrogen bond in S2 is kept.",
 "input_flags": []}
```
