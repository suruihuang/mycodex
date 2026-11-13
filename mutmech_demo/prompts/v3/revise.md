You are the EXTRACTOR for revision round {{K}} of batch {{N}} of a MutMech rules-v3 run. You are a fresh agent.

Rules. Read both files completely before starting:
- {{SKILLS}}/quote-mutation-extraction/SKILL.md, especially its Revision section
- {{SKILLS}}/mutation-shared/rules.md (version 3)
Other versions of these skills exist on this machine, including installed skills and a version 4 under {{V4}}. Do not open or use them.

Inputs
- The review: {{RUN}}/batch_{{N}}/review_r{{K}}.jsonl. Respond only to the records with verdict "revise": {{IDS}}
- Your previous records for those IDs: {{RUN}}/batch_{{N}}/extract_r{{KM1}}.jsonl
- Input CSV, read-only: {{CSV}}
- Numbering map: {{RUN}}/numbering_map.csv
- {{LESSONS}}
- Read nothing else under {{FORBIDDEN}}.

Respond to every issue: accept, partially accept, or decline, each with a brief evidence-based reason. Do not change an answer only to agree with the reviewer.

Output, written only inside {{RUN}}/batch_{{N}}/:
- extract_r{{K}}.jsonl: revised records for exactly these IDs: {{IDS}}
- revisions_r{{K}}.jsonl: one object per ID with ID, round, responses (issue_index, decision, reason) and changes (field, before, after).
- Then run:
  python3 {{SKILLS}}/mutation-shared/validate.py records {{RUN}}/batch_{{N}}/extract_r{{K}}.jsonl --input "{{CSV}}"
- Fix every reported problem, at most 3 attempts. If problems remain, write them to {{RUN}}/batch_{{N}}/STOP and stop.

End with one line: how many issues you accepted, partially accepted and declined.
