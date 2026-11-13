You are running the single-agent BASELINE for batch {{N}} of MutMech. You are a fresh agent working alone: no other agents, earlier rounds or reviews are available to you.

Instructions. Read this file completely before starting, and follow it over anything you remember:
- {{SKILL}}
Other mutation skills exist on this machine, including skills named quote-mutation-extraction, quote-mutation-review and mutation-shared, and copies under eval/. They belong to other methods. Do not open or use them.

Task
- Input CSV, read-only: {{CSV}}
- Process exactly the IDs listed in {{RUN}}/batch_{{N}}/ids.txt, in that order, one record per ID.
- Numbering map: {{RUN}}/numbering_map.csv

Independence
Read only the files named in this prompt. Do not open anything else under {{FORBIDDEN}}, the source workbook under {{WORKBOOK_DIR}}, or any file that contains mechanism labels.

Output
- Write {{RUN}}/batch_{{N}}/mechanisms.jsonl. Write nothing outside {{RUN}}/batch_{{N}}/.

End with one line: the number of records written.
