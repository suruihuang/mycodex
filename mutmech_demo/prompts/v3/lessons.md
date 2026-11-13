You maintain the reflections file of a MutMech rules-v3 run, after batch {{N}}. You are a fresh agent.

Inputs
- The reviewer's proposed general rules for this batch: {{RUN}}/batch_{{N}}/rules_proposed.md
- The current reflections file, which may not exist yet: {{RUN}}/reflections.md
Read nothing else.

Task
- Merge the proposed rules into {{RUN}}/reflections.md as general guidance for the extractor of later batches.
- Deduplicate against the rules already there. Remove ID-specific answer content: a rule may not name record IDs or give the answer for a particular record.
- Keep the file at most 30 lines; merge or drop older rules if necessary.
- Write {{RUN}}/batch_{{N}}/rules_added.json: a JSON list of the rules newly added in this step, or an empty list if none.
Write nothing else.

End with one line: the number of rules added and the line count of reflections.md.
