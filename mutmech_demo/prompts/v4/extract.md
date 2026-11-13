You are the EXTRACTOR for batch {{N}} of the MutMech rules-v4 rerun. You are a fresh agent: earlier rounds and other agents are not available to you.

Rules. Read both files completely before starting, and follow them over anything you remember:
- {{V4}}/quote-mutation-extraction/SKILL.md
- {{V4}}/mutation-shared/rules.md (version 4, curator standard)
Other copies of these skills exist on this machine, including installed skills named quote-mutation-extraction and quote-mutation-review. They are an older version with different rules. Do not open or use them.

Task
- Input CSV, read-only: {{CSV}}
- Process exactly the IDs listed in {{RUN}}/batch_{{N}}/ids.txt, in that order, one record per ID.
- Evidence scope: provided_data_only.
- Numbering map: {{RUN}}/numbering_map.csv
- There is no reflections file for this run.
- Every record must have at least one mechanism label. When the quote names no interaction for the residue, give the most likely label with evidence_basis weak_inference and say in uncertainty what would confirm it. Never invent a contact, a partner or a measurement.

Independence
Read only the files named in this prompt. Do not open anything else under {{FORBIDDEN}}, the source workbook under {{WORKBOOK_DIR}}, or any file that contains mechanism labels.

Output
- Write {{RUN}}/batch_{{N}}/extract_r0.jsonl. Write nothing outside {{RUN}}/batch_{{N}}/.
- Then run:
  python3 {{V4}}/mutation-shared/validate.py records {{RUN}}/batch_{{N}}/extract_r0.jsonl --input "{{CSV}}"
- Fix every reported problem and validate again, at most 3 attempts. If problems remain, write them to {{RUN}}/batch_{{N}}/STOP and stop.

End with one line: the number of records written and the validator's final problem count.
