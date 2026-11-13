#!/usr/bin/env python3
"""One entry point for MutMech method runs: baseline, rules v3 and rules v4 on one dataset, then a comparison.

  python3 -I eval/pipeline/mutmech.py run --dataset DATASET [--methods baseline,v3,v4] [options]
  python3 -I eval/pipeline/mutmech.py compare --name NAME

Methods (each becomes one folder in the run):
  baseline            the single-agent baseline skill: one Codex call per batch, no validator, no reviewer
  v3, v4              extractor, reviewer and up to two revision rounds; v3 also merges the reviewer's
                      proposed rules into a lessons file (reflections.md) that later batches read
  v3-nolessons        v3 with the reviewer but without the lessons file
  v3-norev, v4-norev  extractor only
  stmt                statement rules (skills/stmt): extractor and validator, no reviewer
  --reviewer off turns v3 and v4 into v3-norev and v4-norev; --lessons off turns v3 into v3-nolessons.

Datasets: fullrun (the old full-run batches 1-6), dev, test, reserve (see eval/testset/README.md), or ids:PATH.
Records the curators flagged as data problems ([skipped], [wrong mutation], ...) are left out unless --keep-flagged.

Each role is one fresh `codex exec` call with the same binary and flags as eval/rerun_v4/run.sh. Methods run in
parallel, batches within a method in order. Rerunning the same command resumes: finished steps are kept.
"""
import argparse, collections, datetime, glob, hashlib, json, os, random, re, shutil, subprocess, sys, threading, time

from . import config, codexinfo
from . import gold as sg  # curator tag mapping; metric definitions from evaluate.py
ev = sg.ev

CSV = sg.INPUT
NUMBERING_MAP = config.NUMBERING_MAP
CODEX = config.CODEX
MODEL = config.MODEL
RUNS = os.path.join(config.RUNS, 'pipeline')
BATCH = 25
BASELINE_SKILL = config.BASELINE_SKILL
SKILLS = config.SKILLS
VARIANTS = ('baseline', 'v3', 'v3-nolessons', 'v3-norev', 'v4', 'v4-norev', 'stmt')
LABELS = {sg.HB, sg.EL, sg.HY, sg.AR, sg.ST, sg.CO, sg.CM, sg.OT}
# input tokens seen in earlier runs, per record (lessons: per batch); only for the --dry-run estimate
RATE = {'baseline': 8200, 'extract': 10500, 'review': 15200, 'revise': 1500, 'lessons': 20000}
LOCK = threading.Lock()


class Halt(Exception):
    pass


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def say(msg, path=None):
    line = f'[{now():%Y-%m-%dT%H:%M:%SZ}] {msg}'
    with LOCK:
        print(line, flush=True)
        if path:
            with open(path, 'a', encoding='utf-8') as f:
                f.write(line + '\n')


def jl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def read_ids(path):
    return [x.strip() for x in open(path, encoding='utf-8') if x.strip()]


def labels(r):
    if 'record_class' in r:  # statement rules: stated mechanism, else context, else the inferred guess
        return r.get('mechanism_labels') or r.get('context_labels') or r.get('inferred_labels') or []
    return [x for x in (r.get('mechanism_labels') or []) if x != 'not_stated']


def right(g, M):
    return bool(M and M[0] in g['G']) if g['state'] == 'mechanism' else not M


def usage_limit(events_path):
    for e in jl(events_path) if os.path.exists(events_path) and os.path.getsize(events_path) else []:
        msg = e.get('message') or (e.get('error') or {}).get('message') or ''
        if 'usage limit' in msg.lower():
            return msg
    return ''


# ---------------------------------------------------------------- datasets

def chunk(ids, gold, prefix):
    groups = {}
    for i in ids:
        groups.setdefault(gold[i]['quote'], []).append(i)
    out, cur = [], []
    for g in groups.values():
        if cur and len(cur) + len(g) > BATCH:
            out.append(cur)
            cur = []
        cur += g
    if cur:
        out.append(cur)
    return [(f'{prefix}{k:02d}', b) for k, b in enumerate(out, 1)]


def dataset(name, gold):
    ts = config.TESTSET
    if name == 'fullrun':
        return [(str(n), read_ids(os.path.join(sg.ROOT, 'eval', 'rerun_v4', 'ids', f'batch_{n}.txt'))) for n in range(1, 7)]
    if name == 'test':
        return [(os.path.basename(p)[:-4].replace('test_', 't'), read_ids(p)) for p in sorted(glob.glob(os.path.join(ts, 'batches', 'test_*.txt')))]
    if name in ('dev', 'reserve'):
        return chunk(read_ids(os.path.join(ts, f'{name}_ids.txt')), gold, name[0])
    if name.startswith('ids:'):
        ids = read_ids(name[4:])
        unknown = [i for i in ids if i not in gold]
        if unknown:
            sys.exit(f'IDs not in the input CSV: {unknown[:10]}')
        return chunk(ids, gold, 'c')
    sys.exit(f'unknown dataset {name!r}: use fullrun, dev, test, reserve or ids:PATH')


def pick(batches, spec):
    if not spec:
        return batches
    want = set()
    for part in spec.split(','):
        a, _, b = part.strip().partition('-')
        want |= set(range(int(a), int(b or a) + 1))
    return [bt for k, bt in enumerate(batches, 1) if k in want]


def filtered(batches, gold, keep_flagged, skip_unscorable):
    out, dropped = [], collections.Counter()
    for name, ids in batches:
        keep = []
        for i in ids:
            g = gold[i]
            if not keep_flagged and g['state'] == 'unscorable' and set(g['tags']) & sg.DATA_FLAG:
                dropped['curator data flag'] += 1
            elif skip_unscorable and g['state'] == 'unscorable':
                dropped['unscorable'] += 1
            else:
                keep.append(i)
        if keep:
            out.append([name, keep])
    return out, dict(dropped)


def expand(methods, reviewer, lessons):
    out = []
    for m in (x.strip() for x in methods.split(',') if x.strip()):
        if reviewer == 'off' and m in ('v3', 'v3-nolessons', 'v4'):
            m = m.split('-')[0] + '-norev'
        if lessons == 'off' and m == 'v3':
            m = 'v3-nolessons'
        if m not in VARIANTS:
            sys.exit(f'unknown method {m!r}; choose from {", ".join(VARIANTS)}')
        if m not in out:
            out.append(m)
    return out


def hashes():
    h = {'input_csv': sha(CSV), 'numbering_map': sha(NUMBERING_MAP), 'baseline_skill': sha(BASELINE_SKILL)}
    for v, d in SKILLS.items():
        for f in (('rules.md', 'validate.py') if v == 'stmt' else
                  ('quote-mutation-extraction/SKILL.md', 'quote-mutation-review/SKILL.md', 'mutation-shared/rules.md', 'mutation-shared/validate.py')):
            h[f'{v}/{f}'] = sha(os.path.join(d, f))
    for f in sorted(glob.glob(os.path.join(config.PROMPTS, '*', '*.md'))):
        h['prompts/' + os.path.relpath(f, config.PROMPTS)] = sha(f)
    return h


# ---------------------------------------------------------------- running one method

class Runner:
    def __init__(self, run_dir, variant, dry):
        self.variant, self.dry = variant, dry
        self.base = variant.split('-')[0]
        self.reviewer = self.base in ('v3', 'v4') and not variant.endswith('-norev')
        self.lessons = variant == 'v3'
        self.dir = os.path.join(run_dir, variant)
        self.log = os.path.join(self.dir, 'run.log')
        self.validator = (None if self.base == 'baseline' else os.path.join(SKILLS['stmt'], 'validate.py') if self.base == 'stmt'
                          else os.path.join(SKILLS[self.base], 'mutation-shared', 'validate.py'))
        os.makedirs(os.path.join(self.dir, 'logs'), exist_ok=True)
        if not os.path.exists(os.path.join(self.dir, 'numbering_map.csv')):
            shutil.copy(NUMBERING_MAP, os.path.join(self.dir, 'numbering_map.csv'))

    def bdir(self, batch):
        return os.path.join(self.dir, f'batch_{batch}')

    def lessons_line(self):
        if not self.lessons:
            return 'There is no reflections file for this run.'
        p = os.path.join(self.dir, 'reflections.md')
        if os.path.exists(p) and os.path.getsize(p):
            return f'Reflections file: {p}. It holds general rules learned in earlier batches of this run; apply them as guidance, not as answers for specific IDs.'
        return 'There is no reflections file yet.'

    def fill(self, template, **kw):
        text = open(os.path.join(config.PROMPTS, self.base, template), encoding='utf-8').read()
        values = {'RUN': self.dir, 'CSV': CSV, 'FORBIDDEN': ' or '.join(config.FORBIDDEN),
                  'WORKBOOK_DIR': os.path.dirname(config.WORKBOOK), 'V4': SKILLS['v4'], **kw}
        if self.base == 'baseline':
            values['SKILL'] = BASELINE_SKILL
        elif self.base == 'stmt':
            values['STMT'] = SKILLS['stmt']
        elif self.base == 'v3':
            values['SKILLS'] = SKILLS['v3']
            values['LESSONS'] = self.lessons_line()
        for k, v in values.items():
            text = text.replace('{{' + k + '}}', str(v))
        left = sorted(set(re.findall(r'\{\{(\w+)\}\}', text)))
        if left:
            raise Halt(f'{self.base}/{template}: unfilled placeholders {left}')
        return text

    def codex(self, step, prompt):
        out = os.path.join(self.dir, 'logs', f'{step}.{now():%Y%m%dT%H%M%SZ}')
        open(out + '.prompt.md', 'w', encoding='utf-8').write(prompt)
        if self.dry:
            say(f'{self.variant}: dry run, prompt for {step} written to {out}.prompt.md', self.log)
            return None
        say(f'{self.variant}: start {step}', self.log)
        cmd = [CODEX, 'exec'] + (['-m', MODEL] if MODEL else []) + ['-s', 'workspace-write', '-c', 'approval_policy="never"',
                                                                   '-C', self.dir, '--json', '-o', out + '.last.txt', '-']
        with open(out + '.prompt.md', encoding='utf-8') as fin, open(out + '.events.jsonl', 'w') as fev, open(out + '.stderr.txt', 'w') as ferr:
            rc = subprocess.run(cmd, stdin=fin, stdout=fev, stderr=ferr).returncode
        last = [x.strip() for x in open(out + '.last.txt', encoding='utf-8')] if os.path.exists(out + '.last.txt') else []
        last = [x for x in last if x]
        json.dump(codexinfo.session_info(out + '.events.jsonl'), open(out + '.session.json', 'w', encoding='utf-8'), indent=1)
        say(f'{self.variant}: done {step} (exit {rc}): {last[-1] if last else "no final message"}', self.log)
        return rc, usage_limit(out + '.events.jsonl')

    def step(self, name, check, template, batch, **kw):
        """Run one Codex call unless its output already exists and checks out. Returns False only in a dry run."""
        if check():
            return True
        res = self.codex(name, self.fill(template, N=batch, **kw))
        if res is None:
            return False
        rc, limit = res
        stop = os.path.join(self.bdir(batch), 'STOP')
        if os.path.exists(stop):
            raise Halt(f'STOP in batch {batch}: {open(stop, encoding="utf-8").read().strip()[:300]}')
        if check():
            if rc:
                say(f'{self.variant}: {name} exited {rc}, but its output is complete and valid; keeping it', self.log)
            return True
        if limit:
            raise Halt(f'Codex usage limit during {name}: {limit} Rerun the same command later; finished steps are kept.')
        raise Halt(f'{name} produced no valid output (exit {rc}); see {self.dir}/logs/{name}.*.stderr.txt')

    def done(self, batch, kind, rnd, expected):
        path = os.path.join(self.bdir(batch), f'extract_r{rnd}.jsonl' if kind == 'extract' else f'review_r{rnd}.jsonl')
        if not os.path.exists(path):
            return False
        try:
            got = [str(r.get('ID')) for r in jl(path)]
        except ValueError:
            return False
        if sorted(got) != sorted(expected):
            return False
        r = subprocess.run([sys.executable, '-I', self.validator, 'records' if kind == 'extract' else 'review', path, '--input', CSV],
                           capture_output=True, text=True)
        return r.returncode == 0

    def revise_ids(self, batch, k):
        return [str(v['ID']) for v in jl(os.path.join(self.bdir(batch), f'review_r{k}.jsonl')) if v.get('verdict') == 'revise']

    def write_final(self, batch, final, summary):
        with open(os.path.join(self.bdir(batch), 'final.jsonl'), 'w', encoding='utf-8') as f:
            for r in final:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
        json.dump(summary, open(os.path.join(self.bdir(batch), 'summary.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
        say(f'{self.variant}: batch {batch} final: {json.dumps(summary, ensure_ascii=False)}', self.log)

    def baseline_batch(self, batch, ids):
        out = os.path.join(self.bdir(batch), 'mechanisms.jsonl')

        def check():
            try:
                return set(ids) <= {str(r.get('ID')) for r in jl(out)}
            except ValueError:
                return False
        if not self.step(f'{batch}_baseline', check, 'extract.md', batch):
            return
        recs, dup = {}, []
        for r in jl(out):
            i = str(r.get('ID'))
            if i in recs:
                dup.append(i)
            else:
                recs[i] = r
        final = [dict(recs[i], final_verdict='no reviewer') for i in ids]
        bad = [i for i in ids if not labels(recs[i]) or set(labels(recs[i])) - LABELS]
        # reported, never repaired: the baseline has no validator by design
        self.write_final(batch, final, {'batch': batch, 'records': len(final), 'duplicate_ids': dup,
                                        'ids_not_in_batch': sorted(set(recs) - set(ids)), 'empty_or_unknown_labels': bad})

    def pipeline_batch(self, batch, ids):
        if not self.step(f'{batch}_extract_r0', lambda: self.done(batch, 'extract', 0, ids), 'extract.md', batch):
            return
        if not self.reviewer:
            final = [dict(r, final_verdict='not reviewed', final_round=0) for r in sorted(jl(os.path.join(self.bdir(batch), 'extract_r0.jsonl')), key=lambda r: ids.index(str(r['ID'])))]
            self.write_final(batch, final, {'batch': batch, 'records': len(final), 'reviewer': False})
            return
        if not self.step(f'{batch}_review_r1', lambda: self.done(batch, 'review', 1, ids), 'review.md', batch):
            return
        for k in (1, 2):
            rid = self.revise_ids(batch, k)
            if not rid:
                break
            if not self.step(f'{batch}_revise_r{k}', lambda: self.done(batch, 'extract', k, rid), 'revise.md', batch, K=k, KM1=k - 1, IDS=','.join(rid)):
                return
            if not self.step(f'{batch}_review_r{k + 1}', lambda: self.done(batch, 'review', k + 1, rid), 'rereview.md', batch, K=k, KP1=k + 1, IDS=','.join(rid)):
                return
        recs, verdict, rounds = {}, {}, {}
        for k in range(0, 3):
            for r in jl(os.path.join(self.bdir(batch), f'extract_r{k}.jsonl')):
                recs[str(r['ID'])] = r
                rounds[str(r['ID'])] = k
        for k in range(1, 4):
            for v in jl(os.path.join(self.bdir(batch), f'review_r{k}.jsonl')):
                verdict[str(v['ID'])] = v.get('verdict')
        final, nh = [], []
        for i in ids:
            v = verdict.get(i, 'no review')
            if v in ('revise', 'needs_human'):
                v = 'needs_human'
                nh.append(i)
            final.append(dict(recs[i], final_verdict=v, final_round=rounds[i]))
        self.write_final(batch, final, {'batch': batch, 'records': len(final), 'needs_human': nh,
                                        'basis': dict(collections.Counter(r.get('evidence_basis') for r in final)),
                                        'revised_round1': self.revise_ids(batch, 1), 'revised_round2': self.revise_ids(batch, 2)})
        if len(nh) > 0.2 * len(final):
            raise Halt(f'batch {batch} has {len(nh)} needs_human of {len(final)} (over 20%); check it, then rerun to continue')

    def merge_lessons(self, batch):
        added = os.path.join(self.bdir(batch), 'rules_added.json')
        proposed = os.path.join(self.bdir(batch), 'rules_proposed.md')
        if os.path.exists(added):
            return
        if not (os.path.exists(proposed) and open(proposed, encoding='utf-8').read().strip()):
            json.dump([], open(added, 'w'))
            return

        def check():
            try:
                return isinstance(json.load(open(added, encoding='utf-8')), list)
            except (OSError, ValueError):
                return False
        self.step(f'{batch}_lessons', check, 'lessons.md', batch)

    def run(self, batches):
        try:
            for batch, ids in batches:
                b = self.bdir(batch)
                os.makedirs(b, exist_ok=True)
                idf = os.path.join(b, 'ids.txt')
                if os.path.exists(idf) and read_ids(idf) != ids:
                    raise Halt(f'batch {batch} already holds different IDs; use a new --name')
                open(idf, 'w', encoding='utf-8').write('\n'.join(ids) + '\n')
                if not os.path.exists(os.path.join(b, 'final.jsonl')):
                    (self.baseline_batch if self.base == 'baseline' else self.pipeline_batch)(batch, ids)
                    if self.dry:
                        return 'dry run'
                if self.lessons:
                    self.merge_lessons(batch)
                    if self.dry and not os.path.exists(os.path.join(b, 'rules_added.json')):
                        return 'dry run'
            return 'finished'
        except Halt as e:
            say(f'{self.variant}: STOPPED. {e}', self.log)
            return f'stopped: {e}'


# ---------------------------------------------------------------- run

def cmd_run(a):
    gold, _ = sg.load_gold()
    variants = expand(a.methods, a.reviewer, a.lessons)
    if a.dataset == 'test' and not a.final:
        sys.exit('The test set is scored once per final method. Freeze the rules first, then add --final.')
    batches, dropped = filtered(pick(dataset(a.dataset, gold), a.batches), gold, a.keep_flagged, a.skip_unscorable)
    if not batches:
        sys.exit('no records selected')
    name = a.name or f'{a.dataset.replace(":", "_").replace("/", "_")}-{now():%Y%m%d-%H%M}'
    run_dir = os.path.join(RUNS, name)
    cfg_path = os.path.join(run_dir, 'config.json')
    cfg = {'name': name, 'dataset': a.dataset, 'batch_spec': a.batches, 'keep_flagged': a.keep_flagged,
           'skip_unscorable': a.skip_unscorable, 'dropped': dropped, 'batches': batches}
    h = hashes()
    if os.path.exists(cfg_path):
        old = json.load(open(cfg_path, encoding='utf-8'))
        if old['batches'] != batches:
            sys.exit(f'run {name!r} already exists with different batches; choose another --name')
        changed = sorted(k for k in h if old.get('hashes', {}).get(k) not in (None, h[k]))
        if changed:
            say(f'WARNING: these files changed since this run started: {", ".join(changed)}')
        cfg['created'], cfg['variants'] = old['created'], [v for v in VARIANTS if v in set(old['variants']) | set(variants)]
    else:
        os.makedirs(run_dir, exist_ok=True)
        cfg['created'], cfg['variants'] = f'{now():%Y-%m-%dT%H:%M:%SZ}', variants
    cfg.update({'updated': f'{now():%Y-%m-%dT%H:%M:%SZ}', 'codex': CODEX, 'model': MODEL or 'Codex default', 'hashes': h})
    json.dump(cfg, open(cfg_path, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)

    n = sum(len(ids) for _, ids in batches)
    st = collections.Counter(gold[i]['state'] for _, ids in batches for i in ids)
    say(f'run {name}: dataset {a.dataset}, {len(batches)} batches, {n} records '
        f'({st["mechanism"]} curator mechanism, {st["no_mechanism"]} curator none, {st["unscorable"]} unscorable); left out: {dropped or "none"}')
    rows = []
    for v in variants:
        base = v.split('-')[0]
        if base == 'baseline':
            calls, tok = len(batches), RATE['baseline'] * n
        elif v.endswith('-norev') or base == 'stmt':
            calls, tok = len(batches), RATE['extract'] * n
        else:
            calls = 2 * len(batches)
            tok = (RATE['extract'] + RATE['review'] + RATE['revise']) * n + (RATE['lessons'] * len(batches) if v == 'v3' else 0)
        rows.append([v, f'{calls}+', f'{tok / 1e6:.1f}M'])
    print(ev.table(['Method', 'Codex calls', 'Input tokens, rough (mostly cached)'], rows))
    print(f'Output folder: {run_dir}')

    runners = [Runner(run_dir, v, a.dry_run) for v in variants]
    status = {}
    if a.sequential or a.dry_run:
        for r in runners:
            status[r.variant] = r.run(batches)
    else:
        threads = []
        for r in runners:
            t = threading.Thread(target=lambda r=r: status.__setitem__(r.variant, r.run(batches)), daemon=True)
            t.start()
            threads.append(t)
        while any(t.is_alive() for t in threads):
            time.sleep(2)
    print(ev.table(['Method', 'Status'], [[v, status.get(v, 'not run')] for v in variants]))
    if not a.dry_run and not a.no_compare:
        compare(run_dir)


# ---------------------------------------------------------------- compare

def paired(gold, ra, rb, ids, n=2000, seed=0):
    if not ids:
        return 0.0, 0.0
    clusters = collections.defaultdict(list)
    for i in ids:
        clusters[gold[i]['quote']].append(i)
    keys = sorted(clusters)
    rng = random.Random(seed)
    d = []
    for _ in range(n):
        s = [i for k in rng.choices(keys, k=len(keys)) for i in clusters[k]]
        d.append(100 * sum(rb[i] - ra[i] for i in s) / len(s))
    d.sort()
    return d[int(0.025 * n)], d[int(0.975 * n) - 1]


def pct(k, n):
    return f'{k}/{n} ({100 * k / n:.1f}%)' if n else '–'


def compare(run_dir):
    cfg = json.load(open(os.path.join(run_dir, 'config.json'), encoding='utf-8'))
    gold, inp = sg.load_gold()
    test = cfg['dataset'] == 'test'
    order = [i for _, ids in cfg['batches'] for i in ids]
    finals, r0, sent = {}, {}, {}
    for v in VARIANTS:
        f, e, s = {}, {}, 0
        for batch, _ in cfg['batches']:
            b = os.path.join(run_dir, v, f'batch_{batch}')
            f.update({str(r['ID']): r for r in jl(os.path.join(b, 'final.jsonl'))})
            e.update({str(r['ID']): r for r in jl(os.path.join(b, 'extract_r0.jsonl'))})
            s += sum(1 for x in jl(os.path.join(b, 'review_r1.jsonl')) if x.get('verdict') == 'revise')
        if f:
            finals[v], r0[v], sent[v] = f, e, s
    variants = list(finals)
    out = [f'# Comparison: run `{cfg["name"]}`\n',
           f'Dataset `{cfg["dataset"]}`{" (batches " + cfg["batch_spec"] + ")" if cfg.get("batch_spec") else ""}, '
           f'{len(order)} records in {len(cfg["batches"])} batches. Left out before running: {cfg.get("dropped") or "none"}. '
           f'Model setting: {cfg.get("model")}; models observed in Codex session records: {", ".join(codexinfo.observed_models(run_dir)) or "none recorded"}.\n']
    if not variants:
        out.append('No method has finished a batch yet.\n')
        return finish(run_dir, out, {})
    common = [i for i in order if all(i in finals[v] for v in variants)]
    out.append(ev.table(['Method', 'Records finished'], [[v, f'{sum(i in finals[v] for i in order)}/{len(order)}'] for v in variants]) + '\n')
    out.append(f'All methods are compared on the {len(common)} records every method has finished.\n')
    scored = [i for i in common if gold[i]['state'] != 'unscorable']
    mech = [i for i in scored if gold[i]['state'] == 'mechanism']
    none = [i for i in scored if gold[i]['state'] == 'no_mechanism']
    basis = {v: {i: finals[v][i].get('evidence_basis') for i in common} for v in variants}

    systems = {v: {i: labels(finals[v][i]) for i in common} for v in variants}
    for v in variants:
        if v in ('v3', 'v3-nolessons', 'v4') and all(i in r0[v] for i in common):
            systems[f'{v} (extractor only)'] = {i: labels(r0[v][i]) for i in common}
    systems['keyword rule'] = {i: sg.keyword(inp[i]['Quote']) for i in common}

    out.append('## Accuracy\n')
    out.append(f'{len(scored)} scorable records: {len(mech)} with a curator mechanism, {len(none)} the curators mark as having none.\n')
    out.append('Three ways to count the curator-none records, until one is chosen. **A**: only records with a curator mechanism, '
               'primary label in the curator set. **B**: all scorable records, a weak_inference label counted as no mechanism. '
               '**C**: all scorable records, a label on a curator-none record counted wrong.\n')
    rows, summary = [], {}
    for name, p in systems.items():
        a_ok = sum(right(gold[i], p[i]) for i in mech)
        c_ok = sum(right(gold[i], p[i]) for i in scored)
        blank = sum(1 for i in none if not p[i])
        v = name.split(' ')[0]
        has_basis = v in basis and not name.endswith('(extractor only)') and any(basis[v].values())
        if has_basis:
            pb = {i: ([] if basis[v][i] == 'weak_inference' else p[i]) for i in scored}
            b_ok = sum(right(gold[i], pb[i]) for i in scored)
            weak_none = sum(1 for i in none if basis[v][i] == 'weak_inference')
        rows.append([name, pct(a_ok, len(mech)), pct(b_ok, len(scored)) if has_basis else '–', pct(c_ok, len(scored)),
                     f'{blank}/{len(none)}', f'{weak_none}/{len(none)}' if has_basis else '–'])
        summary[name] = {'A': [a_ok, len(mech)], 'C': [c_ok, len(scored)], 'B': [b_ok, len(scored)] if has_basis else None}
    out.append(ev.table(['System', 'A: curator mechanism, primary hit', 'B: weak_inference as none', 'C: all scorable',
                         'Curator none left blank', 'Curator none marked weak_inference'], rows) + '\n')

    out.append('## Pairwise differences\n')
    rows = []
    for x in range(len(variants)):
        for y in range(x + 1, len(variants)):
            a, b = variants[x], variants[y]
            ra = {i: right(gold[i], systems[a][i]) for i in scored}
            rb = {i: right(gold[i], systems[b][i]) for i in scored}
            dc = 100 * (sum(rb.values()) - sum(ra.values())) / len(scored) if scored else 0
            da = 100 * (sum(rb[i] for i in mech) - sum(ra[i] for i in mech)) / len(mech) if mech else 0
            lo_c, hi_c = paired(gold, ra, rb, scored)
            lo_a, hi_a = paired(gold, ra, rb, mech)
            gained = [i for i in scored if rb[i] and not ra[i]]
            lost = [i for i in scored if ra[i] and not rb[i]]
            ids_txt = (lambda L: str(len(L))) if test else (lambda L: f'{len(L)}: {", ".join(L) or "–"}')
            rows.append([f'{a} → {b}', f'{da:+.1f} [{lo_a:+.1f}, {hi_a:+.1f}]', f'{dc:+.1f} [{lo_c:+.1f}, {hi_c:+.1f}]', ids_txt(gained), ids_txt(lost)])
    if rows:
        out.append(ev.table(['Step', 'A, points [95% interval]', 'C, points [95% interval]', 'Gained', 'Lost'], rows) + '\n')
        out.append('Intervals are paired, quote-clustered bootstraps (2,000 resamples). Gained and lost count records under C.\n')
    out.append(sg.score_block(gold, systems, common, 'Label metrics with 95% quote-clustered intervals'))

    rev = [v for v in variants if v in ('v3', 'v3-nolessons', 'v4')]
    if rev:
        out.append('## Reviewer effect\n')
        rows = []
        for v in rev:
            ids = [i for i in common if i in r0[v]]
            ch = sum(1 for i in ids if labels(r0[v][i]) != labels(finals[v][i]))
            pr = sum(1 for i in ids if labels(r0[v][i])[:1] != labels(finals[v][i])[:1])
            sc = [i for i in ids if gold[i]['state'] != 'unscorable']
            rows.append([v, len(ids), sent[v], ch, pr, pct(sum(right(gold[i], labels(r0[v][i])) for i in sc), len(sc)),
                         pct(sum(right(gold[i], labels(finals[v][i])) for i in sc), len(sc))])
        out.append(ev.table(['Method', 'Records', 'Sent back', 'Labels changed', 'Primary label changed', 'C, extractor only', 'C, final'], rows) + '\n')

    bv = [v for v in variants if v != 'baseline']
    if bv:
        out.append('## By evidence basis\n')
        rows = []
        for v in bv:
            for b, n in collections.Counter(basis[v].values()).most_common():
                ids = [i for i in common if basis[v][i] == b]
                m = [i for i in ids if gold[i]['state'] == 'mechanism']
                rows.append([v, b, n, pct(sum(right(gold[i], systems[v][i]) for i in m), len(m)),
                             sum(1 for i in ids if gold[i]['state'] == 'no_mechanism'), sum(1 for i in ids if gold[i]['state'] == 'unscorable')])
        out.append(ev.table(['Method', 'Basis', 'Records', 'Curator mechanism, primary hit', 'Curator none', 'Unscorable'], rows) + '\n')

    out.append('## Tokens\n')
    rows = []
    for v in variants:
        tot = collections.defaultdict(collections.Counter)
        failed = 0
        for f in glob.glob(os.path.join(run_dir, v, 'logs', '*.events.jsonl')):
            m = re.match(r'^[^_]+_(baseline|extract|review|revise|lessons)', os.path.basename(f))
            role = m.group(1) if m else 'other'
            for e in jl(f) if os.path.getsize(f) else []:
                if e.get('type') == 'turn.completed' and isinstance(e.get('usage'), dict):
                    tot[role].update({k: x for k, x in e['usage'].items() if isinstance(x, int)})
                failed += e.get('type') == 'turn.failed'
        allin = sum(c['input_tokens'] for c in tot.values())
        parts = ', '.join(f'{r} {c["input_tokens"] / 1e3:,.0f}K' for r, c in sorted(tot.items()))
        rows.append([v, f'{allin:,}', f'{allin // max(len(finals[v]), 1):,}', parts or '–', failed])
    out.append(ev.table(['Method', 'Input tokens', 'Per finished record', 'By role', 'Failed calls (tokens not reported)'], rows) + '\n')

    if test:
        out.append('Test set: record-level results are not shown, so that rules are not tuned to test errors.\n')
    else:
        out.append('## Record by record\n')
        rows = []
        for i in common:
            g = gold[i]
            codes = ', '.join(g['G']) or ('none' if g['state'] == 'no_mechanism' else 'unscorable')
            cells = []
            for v in variants:
                M = systems[v][i]
                mark = '' if g['state'] == 'unscorable' else (' ✓' if right(g, M) else ' ✗')
                cells.append((', '.join(M) or '–') + mark)
            rows.append([i, str(g['raw'] or '').replace('|', '/').replace('\n', ' ')[:50], codes] + cells)
        out.append(ev.table(['ID', 'Curator cell', 'Curator codes'] + variants, rows) + '\n')
    return finish(run_dir, out, summary)


def finish(run_dir, out, summary):
    md = '\n'.join(out)
    open(os.path.join(run_dir, 'compare.md'), 'w', encoding='utf-8').write(md)
    json.dump(summary, open(os.path.join(run_dir, 'compare.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    head = md.split('## Pairwise differences')[0]
    print(head.strip())
    print(f'\nFull comparison: {os.path.join(run_dir, "compare.md")}')


def cmd_compare(a):
    run_dir = os.path.join(RUNS, a.name)
    if not os.path.exists(os.path.join(run_dir, 'config.json')):
        sys.exit(f'no run named {a.name!r} under {RUNS}')
    compare(run_dir)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run', help='run methods on a dataset, then compare')
    r.add_argument('--dataset', required=True, help='fullrun | dev | test | reserve | ids:PATH')
    r.add_argument('--methods', default='baseline,v3,v4', help=f'comma-separated, from {", ".join(VARIANTS)}')
    r.add_argument('--reviewer', choices=['on', 'off'], default='on', help='off turns v3 and v4 into extractor-only runs')
    r.add_argument('--lessons', choices=['on', 'off'], default='on', help='v3 only: carry reviewer rules between batches')
    r.add_argument('--batches', default='', help='which batches of the dataset, by position, e.g. 1-3,6')
    r.add_argument('--name', default='', help='run folder name; reuse it to resume or to add methods')
    r.add_argument('--keep-flagged', action='store_true', help='also run records the curators flagged as data problems')
    r.add_argument('--skip-unscorable', action='store_true', help='leave out every record without a scorable curator label')
    r.add_argument('--sequential', action='store_true', help='run methods one after another instead of in parallel')
    r.add_argument('--dry-run', action='store_true', help='write the plan and the first prompt of each method, no model calls')
    r.add_argument('--no-compare', action='store_true')
    r.add_argument('--final', action='store_true', help='required for --dataset test')
    c = sub.add_parser('compare', help='compare the methods of an existing run')
    c.add_argument('--name', required=True)
    a = ap.parse_args()
    (cmd_run if a.cmd == 'run' else cmd_compare)(a)


if __name__ == '__main__':
    main()
