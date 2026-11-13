You are the REVIEWER for re-review round {{KP1}} of batch {{N}} of the MutMech rules-v4 rerun. You are a fresh agent.

Rules. Read both files completely before starting:
- {{V4}}/quote-mutation-review/SKILL.md, especially its Re-review section
- {{V4}}/mutation-shared/rules.md (version 4, curator standard)
Installed skills named quote-mutation-extraction and quote-mutation-review are an older version. Do not open or use them.

Re-review only these IDs: {{IDS}}
- The issues raised in the previous review: {{RUN}}/batch_{{N}}/review_r{{K}}.jsonl
- The revised records: {{RUN}}/batch_{{N}}/extract_r{{K}}.jsonl
- The extractor's responses: {{RUN}}/batch_{{N}}/revisions_r{{K}}.jsonl
- Input CSV, read-only: {{CSV}}
- Numbering map: {{RUN}}/numbering_map.csv
- Read nothing else under {{FORBIDDEN}}.

If the extractor declined an issue with a reason grounded in rules.md and the quote, either accept the record or mark it needs_human with both positions stated. A decline that rests on anything else does not settle the issue. Do not repeat an issue without new evidence.

Output. Never edit records, and write only:
- {{RUN}}/batch_{{N}}/review_r{{KP1}}.jsonl: one verdict for each of these IDs and no others.
- Then run:
  python3 {{V4}}/mutation-shared/validate.py review {{RUN}}/batch_{{N}}/review_r{{KP1}}.jsonl --input "{{CSV}}"
- Fix every reported problem, at most 3 attempts. If problems remain, write them to {{RUN}}/batch_{{N}}/STOP and stop.

End with one line: the verdict counts.
