---
name: mutation-dataset-copy
description: Copy selected rows of the original mutation workbook verbatim to a UTF-8 CSV, with no inference, normalization, or added fields. Use only when asked for a copy of the original mutation dataset.
---

# Mutation dataset copy

- Read the `CLEANED` sheet in `/home/surui-wsl/data/Cleaned quotes +Results.xlsx`, unless the user specifies a different original workbook or sheet.
- Copy `ID`, `PDB`, `Mutation DECODED`, `Quote`, and `Citation` verbatim from the original workbook, matching records by ID. Map the original `Quote 2` column to `Quote`. Preserve blank field values; do not infer, regenerate, or supplement mutations, PDB identifiers, or citations.
- Read and write every value as text (for example pandas `dtype=str`, `keep_default_na=False`), so IDs keep their form and PDB codes such as `1E10` are not parsed as numbers.
- Verify copied field values against the original source and save the copy as an Excel-compatible UTF-8 CSV. Follow the user's requested row selection; do not impose a fixed ID list or record count.
- Keep the original Excel workbook unchanged; write the copy to a separate output file.
