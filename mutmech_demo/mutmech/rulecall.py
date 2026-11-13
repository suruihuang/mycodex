"""Run one rule's extractor prompt through Codex on a one-record run folder and read its record back.

Rules: baseline (the single-agent skill), v4 (rules v4, extractor only, as the v4-norev method) and stmt
(statement rules, no reviewer). The prompts are the batch prompts of `mutmech pipeline` with batch name a1, so a
one-record call follows the same instructions as a batch run. For v4 and stmt the rule's validator is run again
on the written record and its problem count is reported.
"""
import datetime, hashlib, json, os, re, subprocess, sys, time

from . import codexinfo, config, pipeline

NAMES = {'baseline': 'single-agent baseline', 'v4': 'rules v4, extractor only', 'stmt': 'statement rules'}
OUTPUT = {'baseline': 'mechanisms.jsonl', 'v4': 'extract_r0.jsonl', 'stmt': 'extract_r0.jsonl'}


def retry_at(msg):
    """Local time named in a Codex usage-limit message ("try again at 5:26 PM", optionally with a date), as epoch seconds."""
    m = re.search(r'try again at ([^.]*?(\d{1,2}):(\d{2})\s*([AP]M))', msg or '')
    if not m:
        return None
    now = datetime.datetime.now()
    t = now.replace(hour=int(m.group(2)) % 12 + (12 if m.group(4) == 'PM' else 0), minute=int(m.group(3)), second=0, microsecond=0)
    d = re.search(r'([A-Z][a-z]{2})\w* (\d{1,2})(?:st|nd|rd|th)?', m.group(1))
    if d:
        try:
            t = t.replace(month=datetime.datetime.strptime(d.group(1), '%b').month, day=int(d.group(2)))
        except ValueError:
            pass
    while t < now - datetime.timedelta(minutes=5):
        t += datetime.timedelta(days=1)
    return t.timestamp()


def sha(path_or_text, text=False):
    data = path_or_text.encode('utf-8') if text else open(path_or_text, 'rb').read()
    return hashlib.sha256(data).hexdigest()


def skill_files(rule):
    if rule == 'baseline':
        return [config.BASELINE_SKILL]
    if rule == 'v4':
        return [os.path.join(config.SKILLS['v4'], f) for f in
                ('quote-mutation-extraction/SKILL.md', 'mutation-shared/rules.md', 'mutation-shared/validate.py')]
    return [os.path.join(config.SKILLS['stmt'], f) for f in ('rules.md', 'validate.py')]


def validator(rule):
    return {'baseline': None, 'v4': os.path.join(config.SKILLS['v4'], 'mutation-shared', 'validate.py'),
            'stmt': os.path.join(config.SKILLS['stmt'], 'validate.py')}[rule]


def prompt(rule, run, csv_path):
    text = open(os.path.join(config.PROMPTS, rule, 'extract.md'), encoding='utf-8').read()
    values = {'N': 'a1', 'RUN': run, 'CSV': csv_path, 'FORBIDDEN': ' or '.join(config.FORBIDDEN),
              'WORKBOOK_DIR': os.path.dirname(config.WORKBOOK),
              'SKILL': config.BASELINE_SKILL, 'V4': config.SKILLS['v4'], 'STMT': config.SKILLS['stmt']}
    for k, v in values.items():
        text = text.replace('{{' + k + '}}', v)
    if re.search(r'\{\{\w+\}\}', text):
        raise SystemExit(f'unfilled placeholder in prompts/{rule}/extract.md')
    return text


def statements(rec):
    """The statements of a statement-rules record, each with its link to this mutation and its class."""
    out = []
    for s, l in zip(rec.get('statements') or [], rec.get('links') or []):
        out.append({'sid': s.get('sid'), 'span': s.get('span'), 'kind': s.get('kind'), 'interactions': s.get('interactions'),
                     'participants': s.get('participants'), 'effect': s.get('effect'), 'certainty': s.get('certainty'), 'relation': l.get('relation'),
                     'after_substitution': l.get('after_substitution'), 'applies': l.get('applies'), 'class': l.get('class')})
    return out


def read_record(rule, rec):
    labels = pipeline.labels(rec)
    out = {'mechanism_labels': labels, 'primary': labels[0] if labels else None}
    if rule == 'baseline':
        out.update({'mechanism': rec.get('mechanism'), 'explanation': rec.get('reason')})
    elif rule == 'v4':
        out.update({k: rec.get(k) for k in ('mechanism', 'evidence_basis', 'functional_effect', 'uncertainty', 'input_flags')})
        out['explanation'] = rec.get('supporting_evidence')
    else:
        src = next((k for k in ('mechanism_labels', 'context_labels', 'inferred_labels') if rec.get(k)), None)
        out.update({'record_class': rec.get('record_class'), 'label_source': src, 'statements': statements(rec),
                    'functional_effect': rec.get('functional_effect'), 'explanation': rec.get('rationale'),
                    'input_flags': rec.get('input_flags')})
    return out


def run(rule, run_dir, csv_path, dry_run):
    """Fill the rule's prompt, call Codex unless dry_run, and return the result fields for result.json."""
    text = prompt(rule, run_dir, csv_path)
    out = os.path.join(run_dir, 'call')
    open(out + '.prompt.md', 'w', encoding='utf-8').write(text)
    res = {'rule_called': rule, 'versions': {'prompt_sha256': sha(text, text=True),
                                             **{os.path.basename(f) + '_sha256': sha(f) for f in skill_files(rule)}}}
    if dry_run:
        res['status'] = 'dry run: no LLM call'
        return res
    cmd = [config.CODEX, 'exec'] + (['-m', config.MODEL] if config.MODEL else []) + [
        '-s', 'workspace-write', '-c', 'approval_policy="never"', '-C', run_dir, '--json', '-o', out + '.last.txt', '-']
    with open(out + '.prompt.md', encoding='utf-8') as fin, open(out + '.events.jsonl', 'w') as fev, open(out + '.stderr.txt', 'w') as ferr:
        rc = subprocess.run(cmd, stdin=fin, stdout=fev, stderr=ferr).returncode
    st = os.stat(config.CODEX)
    res['engine'] = {'codex': config.CODEX, 'codex_size': st.st_size,
                     'codex_mtime': datetime.datetime.fromtimestamp(st.st_mtime, datetime.timezone.utc).isoformat(),
                     'model_setting': config.MODEL or 'Codex default', 'exit_code': rc,
                     **codexinfo.session_info(out + '.events.jsonl')}
    res['tokens'] = codexinfo.token_usage(out + '.events.jsonl')
    path = os.path.join(run_dir, 'batch_a1', OUTPUT[rule])
    try:
        recs = [json.loads(l) for l in open(path, encoding='utf-8') if l.strip()]
    except (OSError, ValueError):
        recs = []
    rec = next((r for r in recs if str(r.get('ID')) == '1'), None)
    if rec is None:
        limit = pipeline.usage_limit(out + '.events.jsonl')
        if limit:
            at = retry_at(limit)
            when = datetime.datetime.fromtimestamp(at).strftime('%Y-%m-%d %H:%M') if at else 'the time Codex gives'
            res['usage_limit'] = {'message': limit, 'retry_at': at or time.time() + 3600, 'retry_at_text': when}
            res['status'] = f'usage limit: Codex usage limit reached, retry after {when}'
        else:
            res['status'] = f'failed: no record written (exit {rc}); see {out}.stderr.txt'
        return res
    if validator(rule):
        v = subprocess.run([sys.executable, validator(rule), 'records', path, '--input', csv_path], capture_output=True, text=True)
        res['validator_problems'] = [l for l in v.stdout.splitlines() if l.strip()]
    res.update({'status': 'ok', **read_record(rule, rec)})
    return res
