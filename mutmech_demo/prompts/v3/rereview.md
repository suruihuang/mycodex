You are the REVIEWER for re-review round {{KP1}} of batch {{N}} of a MutMech rules-v3 run. You are a fresh agent.

Rules. Read both files completely before starting:
- {{SKILLS}}/quote-mutation-review/SKILL.md, especially its Re-review section
- {{SKILLS}}/mutation-shared/rules.md (version 3)
Other versions of these skills exist on this machine, including installed skills and a version 4 under {{V4}}. Do not open or use them.

Re-review only these IDs: {{IDS}}
- The issues raised in the previous review: {{RUN}}/batch_{{N}}/review_r{{K}}.jsonl
- The revised records: {{RUN}}/batch_{{N}}/extract_r{{K}}.jsonl
- The extractor's responses: {{RUN}}/batch_{{N}}/revisions_r{{K}}.jsonl
- Input CSV, read-only: {{CSV}}
- Numbering map: {{RUN}}/numbering_map.csv
- Read nothing else under {{FORBIDDEN}}.

If the extractor declined an issue with an evidence-based reason, either accept the record or mark it needs_human with both positions stated. Do not repeat an issue without new evidence.

Output. Never edit records, and write only:
- {{RUN}}/batch_{{N}}/review_r{{KP1}}.jsonl: one verdict for each of these IDs and no others.
- Then run:
  python3 {{SKILLS}}/mutation-shared/validate.py review {{RUN}}/batch_{{N}}/review_r{{KP1}}.jsonl --input "{{CSV}}"
- Fix every reported problem, at most 3 attempts. If problems remain, write them to {{RUN}}/batch_{{N}}/STOP and stop.

End with one line: the verdict counts.
