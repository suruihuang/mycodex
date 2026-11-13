You are the EXTRACTOR for batch {{N}} of the MutMech statement-rules run. You are a fresh agent working alone: no other agents, earlier rounds or reviews are available to you.

Rules. Read this file completely before starting, and follow it over anything you remember:
- {{STMT}}/rules.md (statement rules, draft 1)
Other mutation skills exist on this machine, including skills named quote-mutation-extraction, quote-mutation-review and mutation-shared, and copies under eval/. They follow different rules. Do not open or use them.

Task
- Input CSV, read-only: {{CSV}}
- Process exactly the IDs listed in {{RUN}}/batch_{{N}}/ids.txt, in that order, one record per ID.
- Allowed evidence: the supplied fields, the numbering map and general residue chemistry, as rules.md says.
- Numbering map: {{RUN}}/numbering_map.csv

Procedure
1. Group the batch's IDs by quote text. For each distinct quote, write its statements once, from the quote alone, and reuse the identical list in every record with that quote.
2. For each record, decode the substitution, then judge relation, after_substitution and applies for every statement.
3. Derive each statement's class, the record class and the three label lists by the rules. Computing these derived fields with a short script is fine; the judgments in step 2 are yours.
4. Write functional_effect, rationale and input_flags.

Independence
Read only the files named in this prompt. Do not open anything else under {{FORBIDDEN}}, the source workbook under {{WORKBOOK_DIR}}, or any file that contains mechanism labels.

Output
- Write {{RUN}}/batch_{{N}}/extract_r0.jsonl. Write nothing outside {{RUN}}/batch_{{N}}/.
- Then run:
  python3 {{STMT}}/validate.py records {{RUN}}/batch_{{N}}/extract_r0.jsonl --input "{{CSV}}"
- Fix every reported problem and validate again, at most 3 attempts. If problems remain, write them to {{RUN}}/batch_{{N}}/STOP and stop.

End with one line: the number of records written, the number of distinct quotes, and the validator's final problem count.
