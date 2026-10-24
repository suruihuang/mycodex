# Independent quote-consistency review

Reviewed all 50 source records (source Excel rows 2–51; IDs 6–101) in each of the three requested workbooks: 150 source/workbook assessments and 360 Results data rows (120 per workbook). There are 36 distinct verbatim quotes; duplicated quotes remain separately accounted for in coverage.csv. All 360 result quotes match the corresponding original input verbatim, all PDB fields say Not stated, and all 240 trial Mechanism cells contain a single whitespace-delimited word. Original prose mechanisms were permitted and were not judged against the trial format.

This is a quote-consistency review, not ground-truth accuracy or verification of the underlying science. I read the supplied skill as methodological guidance and inspected only the three requested output workbooks and the first 50 original input records. I did not consult papers, the web, reference answers, other datasets, prior extraction scripts, mechanism_comparison.csv, or another reviewer’s work. Evidence is restricted to each source row’s own quote; matching quotes were reviewed together for efficiency without enriching one quote from another.

## Main conclusion

No clear unsupported substitution, fabricated PDB assignment, incorrect numerical value, protein misassignment, or definite combined-mutant splitting error was identified. The Results and Reasons generally agree and preserve the limits of the excerpts. The five structured findings are caveats across three issue families, not five confirmed scientific errors. There are no clear-error findings.

The most useful refinement is trial 1’s Dispersion label (IDs 81, 97, 101): the quotes establish van der Waals contacts, whereas Dispersion is a narrower interpretation. Its Reason openly defines the shorthand, so this is a terminology ambiguity, not a contradiction. Trial 2’s VanderWaals is closer to the quote. Across all three outputs, the hormone Arg/Glu conversions are separated into decoded substitutions while independent testing is explicitly unverified. The caveats are adequate for reading, but downstream row counts should not be treated as independent experiments. The original output’s H8A/Q12A Ki increases are a plausible contextual inference; the trials’ word changes is more literal.

## Checks that passed and interpretive distinctions

- Contact-only descriptions do not invent mutations. IDs 6, 12, 13, 16, 25, 29, 33, 52, 54, 56, 58 and the later structural-contact quotes appropriately retain missing substitutions. Hydrogenbonding, Saltbridge, Packing and Complementarity describe the quoted interactions or interface when no mutation exists; they must not be interpreted as proven mutation mechanisms in isolation from Mutation DECODED and Reason.
- IDs 7, 10, 42, 44, 45, 47, 48 and 49 keep the approximate twofold on-rate effects at group level and describe electrostatic guidance as an author proposal. Hormone identity is not improperly filled in as hGH.
- IDs 53, 55 and 57 correctly decode R43L and R43M with respective 0.5 and 1 kcal/mol destabilization. R43A follows the same paragraph’s alanine-substitution reference; this contextual decoding is reasonable. Packing is supported by the author’s explicit intramolecular explanation. The label need not mean the Leu/Met replacements themselves were shown structurally to disrupt packing. The original and trial 1 retain the contextual greater-than-2.1 contribution; trial 2 omits that bound without asserting a conflicting number.
- S219A (ID 65) retains unknown protein and an unchanged-affinity observation without a fabricated mechanism. ID 78 reasonably assigns E108A to Ang using the same quote, while His114 and Tyr437 proteins/replacements remain unresolved. IDs 79, 80 and 87 preserve missing replacement identities rather than assuming alanine. Nine residue modifications need not be inferred to be one joint mutant; the quotes do not state such a construct.
- ID 81 and its duplicate ID 97 correctly assign Trp261/Lys320 to hRI and His84/Glu108 to Ang. Missing replacement identities remain missing.
- ID 82 keeps des(460), H8A and Q12A distinct, with 8.5-, 4.6- and 1.6-fold values correctly associated. Reading des(460) as deletion of the named Ser460 is a reasonable stated notation-based inference. Hydrogenbonding reflects the explicitly named partners and author explanation, not independently verified mutant structures.
- ID 84’s corrupted interleaving yields only readable Ang R5A; no Asp41–Lys320 hydrogen bond is misassigned as the R5A mechanism. ID 95 correctly treats the 50-fold dissociation-constant change as equilibrium binding, not an off-rate.
- ID 86 correctly separates K40Q, D435A and their joint complex. Only K40Q receives 1300-fold weakening; D435A remains approximately comparable without an invented exact value. The joint dissociation-rate result is not converted to equilibrium affinity. Saltbridge is supported explicitly by the quote despite its earlier hydrogen-bond hypothesis.
- Mixed contact quotes can reasonably receive Hydrogenbonding while their Reasons preserve accompanying van der Waals interactions. The one-word constraint prevents exhaustive chemistry in the Mechanism cell; that is not itself an extraction error.
- ID 94 leaves the antecedent of “This change” unresolved; a hydrogen-bond explanation is quoted but R5A is not borrowed from adjacent evidence. ID 100’s Hydrophobic is acceptable as author-associated burial because its Reason preserves grouped energy/area ranges and complex-formation context, without asserting a mutant structural measurement.
- OCR artifacts, incomplete thermodynamic symbols, missing proteins, residue numbering, and absent PDB evidence are generally handled conservatively. No structural identity was inferred from citation filenames. Apparent scientific peculiarities in original quotes were not corrected using outside knowledge.

## Detailed caveats

### F01: Dispersion is narrower than the quoted interaction category

Workbook: `agent_trial_1/results.xlsx`. Source IDs: 81,97,101. Results Excel rows: 81–84;112–115;121. Classification: Reasonable but ambiguous terminology.

Quoted evidence: “these residues form only van der Waals contacts; making a total of 15 van der Waals contacts”

The Reason explicitly uses Dispersion as a label for van der Waals contacts. This is understandable as a controlled shorthand, but the quote does not distinguish dispersion from the broader contact category or identify a dispersion-specific causal contribution. It is not a fabricated contact or mutation.

Conservative refinement: Use VanderWaals, as trial 2 does, or document that Dispersion is a broad tagging convention rather than a separately established physical mechanism.

### F02: Separate decoded substitutions do not establish independent mutant experiments

Workbook: `experiment_results/first50_quote_only_mutations.xlsx`. Source IDs: 7,10,42,44,45,47,48,49. Results Excel rows: 3–12;19–48. Classification: Acknowledged evidence ambiguity.

Quoted evidence: “The conversion of three Arg side chains (R64, R167, and R178) to Ala ... The conversion of two Glu side-chains (E65 and E174) to Ala”

All three Reasons correctly disclose uncertainty about single versus combined constructs, and preserve group-level approximate on-rates. Thus this is not a demonstrated grouping error. However, five rows per quote can be mistaken downstream for five verified independent tests. Neither a confirmed multiple mutant nor five confirmed separate experiments follows unambiguously from this isolated sentence.

Conservative refinement: Keep the decoded rows only with an explicit unverified-test-design flag, or use two grouped descriptions with individual substitutions enumerated and test design unresolved. Do not invent a combined construct or individual quantitative values.

### F03: Separate decoded substitutions do not establish independent mutant experiments

Workbook: `agent_trial_1/results.xlsx`. Source IDs: 7,10,42,44,45,47,48,49. Results Excel rows: 3–12;19–48. Classification: Acknowledged evidence ambiguity.

Quoted evidence: “The conversion of three Arg side chains (R64, R167, and R178) to Ala ... The conversion of two Glu side-chains (E65 and E174) to Ala”

All three Reasons correctly disclose uncertainty about single versus combined constructs, and preserve group-level approximate on-rates. Thus this is not a demonstrated grouping error. However, five rows per quote can be mistaken downstream for five verified independent tests. Neither a confirmed multiple mutant nor five confirmed separate experiments follows unambiguously from this isolated sentence.

Conservative refinement: Keep the decoded rows only with an explicit unverified-test-design flag, or use two grouped descriptions with individual substitutions enumerated and test design unresolved. Do not invent a combined construct or individual quantitative values.

### F04: Separate decoded substitutions do not establish independent mutant experiments

Workbook: `agent_trial_2/results.xlsx`. Source IDs: 7,10,42,44,45,47,48,49. Results Excel rows: 3–12;19–48. Classification: Acknowledged evidence ambiguity.

Quoted evidence: “The conversion of three Arg side chains (R64, R167, and R178) to Ala ... The conversion of two Glu side-chains (E65 and E174) to Ala”

All three Reasons correctly disclose uncertainty about single versus combined constructs, and preserve group-level approximate on-rates. Thus this is not a demonstrated grouping error. However, five rows per quote can be mistaken downstream for five verified independent tests. Neither a confirmed multiple mutant nor five confirmed separate experiments follows unambiguously from this isolated sentence.

Conservative refinement: Keep the decoded rows only with an explicit unverified-test-design flag, or use two grouped descriptions with individual substitutions enumerated and test design unresolved. Do not invent a combined construct or individual quantitative values.

### F05: Direction of individual Ki effects is inferred rather than restated verbatim

Workbook: `experiment_results/first50_quote_only_mutations.xlsx`. Source IDs: 82. Results Excel rows: 86–87. Classification: Reasonable contextual inference.

Quoted evidence: “The 8.5-fold increase in Ki ... relative changes produced by substituting these residues individually by Ala (4.6- and 1.6-fold, respectively)”

The original calls the H8A and Q12A changes relative increases in Ki. The quote explicitly gives direction for the deletion and only relative changes for the individual substitutions. The contextual increase reading is very plausible; Reason discloses inference of the endpoint but does not separately label inference of direction. Trial outputs use change and are more literal.

Conservative refinement: Say respective 4.6-fold and 1.6-fold changes in the Ki comparison; direction inferred from context. Preserve the explicit 8.5-fold increase for des(460).

## Artifacts and limits

findings.csv records the five workbook-specific caveats. coverage.csv lists every one of the 150 source/workbook assessments, source IDs, actual Results row ranges, and linked findings. A no-issue assessment means no material contradiction was found against that quote, not that the source science, full paper, PDB mapping, or omitted experimental details have been verified. The workbooks were not modified.
