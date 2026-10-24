#!/usr/bin/env python3
"""Validate mutation sites and generate a browser-based structure annotation."""

import argparse
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

from Bio.PDB import MMCIFParser, PDBIO, PDBParser
from Bio.SeqUtils import seq1


def annotate(model, specification, role):
    """Resolve CHAIN:R64A or CHAIN:D164 using author residue numbering."""
    match = re.fullmatch(
        r"([^:]+):([ACDEFGHIKLMNPQRSTVWY])(-?\d+)(?:\^([A-Za-z]))?([ACDEFGHIKLMNPQRSTVWY])?",
        specification,
    )
    if not match:
        raise ValueError(
            f"Invalid site {specification!r}; use CHAIN:R64A or CHAIN:D164 (insertion code: CHAIN:R64^BA)."
        )
    chain, original, number, insertion, replacement = match.groups()
    chain = " " if chain == "_" else chain
    residue_id = (" ", int(number), insertion or " ")
    if chain not in model or residue_id not in model[chain]:
        raise ValueError(
            f"{specification}: residue has no standard amino-acid coordinates in the selected model."
        )
    residue = model[chain][residue_id]
    observed = seq1(residue.resname, undef_code="?")
    if observed != original:
        raise ValueError(
            f"{specification}: structure contains {residue.resname}, not {original}; check numbering, chain, or deposited mutations."
        )
    if role == "mutation" and not replacement:
        raise ValueError(
            f"{specification}: mutation requires a replacement amino acid."
        )
    if role == "partner" and replacement:
        raise ValueError(
            f"{specification}: partner should identify a residue without a substitution."
        )
    if replacement == original:
        raise ValueError(
            f"{specification}: original and replacement amino acids are identical."
        )
    atoms = list(residue.get_atoms())
    anchor = residue["CA"] if "CA" in residue else atoms[0]
    return {
        "label": specification,
        "role": role,
        "selection": {
            "chain": chain,
            "resi": int(number),
            "icode": insertion or " ",
        },
        "position": dict(zip(("x", "y", "z"), map(float, anchor.coord))),
        "observed": residue.resname,
    }


def build_payload(path, specifications, partners, model_number, title, citation):
    parser = (
        MMCIFParser(QUIET=True)
        if path.suffix.lower() in (".cif", ".mmcif")
        else PDBParser(QUIET=True)
    )
    structure = parser.get_structure("structure", str(path))
    models = list(structure)
    if not 1 <= model_number <= len(models):
        raise ValueError(f"Model must be between 1 and {len(models)}.")
    model = models[model_number - 1]
    annotations = [annotate(model, site, "mutation") for site in specifications]
    annotations += [annotate(model, site, "partner") for site in partners]
    # The browser receives exactly the model and author numbering validated here.
    # PDB serialization fails explicitly for chains/indices it cannot represent.
    output = io.StringIO()
    writer = PDBIO()
    writer.set_structure(model)
    writer.save(output)
    chains = [
        {
            "chain": chain.id.strip() or "_",
            "residues": sum(r.id[0] == " " for r in chain),
        }
        for chain in model
    ]
    return {
        "title": title or path.name,
        "citation": citation,
        "source": path.name,
        "model": model_number,
        "pdb": output.getvalue(),
        "annotations": annotations,
        "chains": chains,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--structure", type=Path, help="Local .pdb, .cif, or .mmcif file"
    )
    source.add_argument(
        "--pdb", help="Four-character PDB accession to download from RCSB"
    )
    parser.add_argument(
        "--mutation",
        action="append",
        default=[],
        help="Repeatable CHAIN:R64A; use _ for blank chain",
    )
    parser.add_argument(
        "--partner", action="append", default=[], help="Repeatable CHAIN:D164"
    )
    parser.add_argument(
        "--model", type=int, default=1, help="One-based model index (default: 1)"
    )
    parser.add_argument("--title", default="")
    parser.add_argument(
        "--citation",
        default="",
        help="Evidence or construct notes displayed alongside the structure",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        path = args.structure
        if args.pdb:
            if not re.fullmatch(r"[0-9][A-Za-z0-9]{3}", args.pdb):
                raise ValueError(
                    "Expected a four-character PDB accession, such as 1A22."
                )
            import tempfile

            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / f"{args.pdb.upper()}.cif"
                with urllib.request.urlopen(
                    f"https://files.rcsb.org/download/{path.name}", timeout=30
                ) as response:
                    path.write_bytes(response.read())
                payload = build_payload(
                    path,
                    args.mutation,
                    args.partner,
                    args.model,
                    args.title,
                    args.citation,
                )
        else:
            payload = build_payload(
                path, args.mutation, args.partner, args.model, args.title, args.citation
            )
        template = Path(__file__).resolve().parent.parent / "assets" / "viewer.html"
        # Escaping '<' prevents source text from terminating the JSON script element.
        serialized = json.dumps(payload).replace("<", "\\u003c")
        document = template.read_text().replace("__STRUCTURE_DATA__", serialized)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(document, encoding="utf-8")
        print(f"Saved {args.output.resolve()}")
        print(
            "Chains (author IDs): "
            + ", ".join(
                f"{c['chain']} ({c['residues']} residues)" for c in payload["chains"]
            )
        )
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
