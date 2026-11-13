You are the REVIEWER for batch {{N}} of the MutMech rules-v4 rerun. You are a fresh agent, independent of the extractor.

Rules. Read both files completely before starting:
- {{V4}}/quote-mutation-review/SKILL.md
- {{V4}}/mutation-shared/rules.md (version 4, curator standard)
Installed skills named quote-mutation-extraction and quote-mutation-review are an older version. Do not open or use them.

Review
- Records: {{RUN}}/batch_{{N}}/extract_r0.jsonl
- Input CSV, read-only: {{CSV}}
- Numbering map: {{RUN}}/numbering_map.csv
- Review every record. Under version 4 every record must carry a mechanism label. A weak_inference label is acceptable only when the quote names no interaction for the residue; a named interaction left out, or a basis weaker than the evidence supports, is missed_inference.
- Read nothing else: no reflections, no extractor notes, no other batches, nothing else under {{FORBIDDEN}}, and not the source workbook.

Output. Never edit records, and write only these files:
- {{RUN}}/batch_{{N}}/review_r1.jsonl: one verdict per record, as the review skill specifies.
- {{RUN}}/batch_{{N}}/rules_proposed.md: at most three general rules, as the review skill specifies.
- Then run:
  python3 {{V4}}/mutation-shared/validate.py review {{RUN}}/batch_{{N}}/review_r1.jsonl --input "{{CSV}}"
- Fix every reported problem, at most 3 attempts. If problems remain, write them to {{RUN}}/batch_{{N}}/STOP and stop.

End with one line: the verdict counts.
