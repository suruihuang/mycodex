---
name: quote-to-pdb-mutation
description: Extract evidence-supported PDB identifiers, decoded mutations, and mechanisms from scientific quotes and papers into an Excel-compatible table. Use when linking mutation evidence to protein structures or preparing mutation extraction spreadsheets.
---

# Quote to PDB mutation

Accept a scientific quote, with any supplied PDF, paper text, DOI, URL, or structure file. Produce an Excel workbook with the columns below. Ask for source information when necessary; do not require a PDF if accessible full text or supplied excerpts provide the evidence.

## Evidence and source handling

- Extract supported information immediately. When the quote does not identify the protein, structure, or mutation sufficiently, request the source paper or relevant sections. In a terminal interface, accept an accessible local PDF path; do not assume graphical attachment controls exist.
- Verify PDB identifiers from a deposition statement or an authoritative PDB record linked to the paper. Never assign an identifier solely from a filename, title, or residue numbers.
- Distinguish structures deposited by the paper from structures cited for comparison. A functional mutant need not have its own deposited structure.
- Preserve page, section, table, or figure references for evidence. Cite the source actually inspected. Disclose inaccessible sources rather than claiming to have read them.
- Record absent information as "Not stated" and unresolved assignments as "Unverified". Flag ambiguous OCR, especially residue identities, accession codes, and measurements. Explain any OCR normalization used to make an assignment.

## Mutation and mechanism interpretation

- Decode each substitution with the affected protein, original amino acid, residue number, and replacement. Example: hGH R64A — human growth hormone Arg64 → Ala.
- Residue contacts alone do not specify a mutation. For "R64 interacts with D164 and E44", record the interaction partners without inventing substitutions.
- Distinguish the mutation in the crystallized construct from mutations tested in functional experiments. Do not present a structural template as an experimentally determined structure of every mutant.
- Use one row per individually tested mutation. Keep a jointly tested multiple-mutant construct in one row; do not distribute its measured effect among its component mutations.
- Preserve paper numbering. Assign chains and PDB residue numbers only after verifying the mapping, including insertion codes and missing residues.
- Connect molecular interactions to reported behavior where supported. Distinguish experimental observations, author-proposed mechanisms, and additional inferences explicitly.
- Keep association rate, dissociation rate, equilibrium affinity, and signaling activity distinct. Do not invent individual values from a grouped result or infer one measurement from another without sufficient data.

## Excel output

Use these exact columns, in this order:

| PDB | Mutation DECODED | Mechanism | Citation | Quote | Reason |
| --- | --- | --- | --- | --- | --- |

- **PDB:** Verified identifier(s), with their relationship to the experiment where relevant; otherwise "Not stated" or "Unverified".
- **Mutation DECODED:** Protein and decoded substitution. If no mutation is specified, use "None specified — residue interaction only" or an appropriate explanation.
- **Mechanism:** Concise supported mechanism and relevant observed effect, identifying hypotheses or inferences.
- **Citation:** Paper identity, available DOI/PMID or URL, and location supporting the row. Identify separate sources when structural and functional evidence differ.
- **Quote:** Preserve the supplied quote verbatim. Label any additional supporting excerpts separately; do not silently replace the original wording with corrected OCR.
- **Reason:** Explain the evidence connecting the PDB, mutation, and mechanism, including construct differences and remaining uncertainty.

Create an .xlsx workbook when tools permit, with wrapped text, readable column widths, a frozen header, and filters. Write extracted content as literal strings rather than spreadsheet formulas. Provide the saved file path. If workbook creation is unavailable, return a TSV with the same headers and clearly state that no workbook was created.

Use available tools rather than requiring a fixed stack. For Python workflows, PyMuPDF can extract PDF text with page references, openpyxl can write workbooks, requests can retrieve records, and Biopython can parse PDB/mmCIF files. Use OCR only when needed and review uncertain recognition results. Do not install visualization dependencies unless visualization is requested.

## Optional structure visualization

When requested, retrieve the verified structure or use a supplied PDB/mmCIF file. Map protein identity and paper numbering to the correct chain and residue before highlighting the mutation site and interaction partners. Report any mapping uncertainty or missing coordinates.

Distinguish three outputs:
- Site annotation: highlight where a mutation occurs on the available structure.
- Modeled mutant: build a replacement side chain and label the result as a prediction, not an experimentally validated conformation.
- Structure overlay: align separate structures using corresponding protein regions and identify the entries and chains used.

Identify mutations already present in the deposited construct. Tools such as py3Dmol can display and annotate structures; PyMOL can support alignment and side-chain modeling. Produce a viewable artifact or reproducible viewer script when available.

### Bundled visualizer

Use `scripts/visualize.py` with Python 3.10+ and Biopython (`python3 -m pip install -r requirements.txt`). It accepts local PDB/mmCIF files or downloads a four-character accession with `--pdb`. The HTML embeds the validated coordinates and loads pinned 3Dmol.js 2.5.3 from jsDelivr; viewing requires internet access and WebGL. Controls support site focus, full-structure zoom, labels, and PNG export.

Run from this skill directory:

```bash
python3 scripts/visualize.py --pdb 1A22 \
  --mutation A:R64A \
  --partner B:D364 --partner B:E244 --partner B:W369 \
  --title '1A22: hGH R64A site' \
  --citation 'PMID 9571026. Deposited hormone is G120R. Receptor paper D164/E44/W169 map to B:D364/E244/W369.' \
  --output 1A22-R64A.html
```

For local input, replace `--pdb 1A22` with `--structure path/to/structure.cif`. Omit site arguments to inspect the whole structure first. Use `--model 2` to select the second coordinate model. Site syntax uses author chain IDs and residue numbers: `A:R64A`, partner `B:D364`, or insertion code `A:R64^BA` (Arg64, insertion B, to Ala). `_` denotes a blank chain. The tool rejects missing coordinates or mismatched original amino acids. Multi-character mmCIF chain IDs and indices beyond legacy PDB limits cannot be serialized by this viewer and require another viewer; do not silently renumber them.

For 1A22, chain A is hormone and chain B is receptor. Receptor author numbering is offset by +200 relative to the paper. Verify this mapping anew for other entries; never apply the offset generally. The deposited Arg120 is the G120R construct, so `A:G120R` correctly fails the original-residue check. Explain already-present mutations in the citation notes rather than pretending to model them.

Run validation tests with `python3 -m unittest discover -s scripts -p 'test_*.py'`. These exercise coordinate identity, insertion codes, missing sites, and model selection. API reference: https://3dmol.org/doc/GLViewer.html.
