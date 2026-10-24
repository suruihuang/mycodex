import tempfile
import unittest
from pathlib import Path

from Bio.PDB import Atom, Chain, Model, Residue
import numpy as np

from visualize import annotate, build_payload


class SiteTests(unittest.TestCase):
    def setUp(self):
        self.model = Model.Model(0)
        chain = Chain.Chain("A")
        self.model.add(chain)
        for insertion, name in [(" ", "ARG"), ("B", "ASP")]:
            residue = Residue.Residue((" ", 64, insertion), name, "")
            chain.add(residue)
            residue.add(
                Atom.Atom(
                    "CA",
                    np.array([1.0, 2.0, 3.0]),
                    1.0,
                    1.0,
                    " ",
                    " CA ",
                    1,
                    element="C",
                )
            )

    def test_substitution_preserves_coordinates(self):
        result = annotate(self.model, "A:R64A", "mutation")
        self.assertEqual(
            result,
            {
                "label": "A:R64A",
                "role": "mutation",
                "selection": {"chain": "A", "resi": 64, "icode": " "},
                "position": {"x": 1.0, "y": 2.0, "z": 3.0},
                "observed": "ARG",
            },
        )
        self.assertEqual(self.model["A"][64].resname, "ARG")

    def test_insertion_code(self):
        self.assertEqual(
            annotate(self.model, "A:D64^BA", "mutation")["selection"],
            {"chain": "A", "resi": 64, "icode": "B"},
        )

    def test_wrong_identity_missing_coordinates_and_invalid_mutation(self):
        for site in ("A:G64A", "B:R64A", "A:R65A", "A:R64", "A:R64R"):
            with self.subTest(site=site), self.assertRaises(ValueError):
                annotate(self.model, site, "mutation")

    def test_local_pdb_model_and_partner(self):
        from Bio.PDB import PDBIO

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.pdb"
            writer = PDBIO()
            writer.set_structure(self.model)
            writer.save(str(path))
            result = build_payload(
                path, ["A:R64A"], ["A:D64^B"], 1, "Example", "Evidence"
            )
            self.assertEqual(
                [a["observed"] for a in result["annotations"]], ["ARG", "ASP"]
            )
            with self.assertRaises(ValueError):
                build_payload(path, [], [], 2, "", "")


if __name__ == "__main__":
    unittest.main()
