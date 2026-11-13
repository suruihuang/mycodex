You are the EXTRACTOR for revision round {{K}} of batch {{N}} of the MutMech rules-v4 rerun. You are a fresh agent.

Rules. Read both files completely before starting:
- {{V4}}/quote-mutation-extraction/SKILL.md, especially its Revision section
- {{V4}}/mutation-shared/rules.md (version 4, curator standard)
Installed skills named quote-mutation-extraction and quote-mutation-review are an older version. Do not open or use them.

Inputs
- The review: {{RUN}}/batch_{{N}}/review_r{{K}}.jsonl. Respond only to the records with verdict "revise": {{IDS}}
- Your previous records for those IDs: {{RUN}}/batch_{{N}}/extract_r{{KM1}}.jsonl
- Input CSV, read-only: {{CSV}}
- Numbering map: {{RUN}}/numbering_map.csv
- Read nothing else under {{FORBIDDEN}}.

Respond to every issue: accept, partially accept, or decline. A decline must rest on rules.md and the quote, and must say which rule. Do not change an answer only to agree with the reviewer. Every record must keep at least one mechanism label.

Output, written only inside {{RUN}}/batch_{{N}}/:
- extract_r{{K}}.jsonl: revised records for exactly these IDs: {{IDS}}
- revisions_r{{K}}.jsonl: one object per ID with ID, round, responses (issue_index, decision, reason) and changes (field, before, after).
- Then run:
  python3 {{V4}}/mutation-shared/validate.py records {{RUN}}/batch_{{N}}/extract_r{{K}}.jsonl --input "{{CSV}}"
- Fix every reported problem, at most 3 attempts. If problems remain, write them to {{RUN}}/batch_{{N}}/STOP and stop.

End with one line: how many issues you accepted, partially accepted and declined.
