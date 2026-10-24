---
name: pdb-mutation-visualizer
description: Render a verified PDB/mmCIF structure with mutation sites and interaction partners highlighted, using the bundled 3Dmol viewer script; also covers modeled mutants and structure overlays. Use when asked to visualize, highlight, model, or overlay mutation sites on a structure.
---

# PDB mutation visualizer

Retrieve the verified structure or use a supplied PDB/mmCIF file. Map protein identity and paper numbering to the correct chain and residue before highlighting the mutation site and interaction partners. Report any mapping uncertainty or missing coordinates.

Distinguish three outputs:
- Site annotation: highlight where a mutation occurs on the available structure.
- Modeled mutant: build a replacement side chain and label the result as a prediction, not an experimentally validated conformation.
- Structure overlay: align separate structures using corresponding protein regions and identify the entries and chains used.

Identify mutations already present in the deposited construct. Tools such as py3Dmol can display and annotate structures; PyMOL can support alignment and side-chain modeling. Produce a viewable artifact or reproducible viewer script when available. Install visualization dependencies only for this skill's tasks.

## Bundled visualizer

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
