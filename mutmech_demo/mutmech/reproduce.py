"""Check that this repository reproduces the numbers logged in eval/LOG.md (2026-11-05 to 11-10).

No LLM calls: routing v1 reuses the LLM labels of the dev run named by `dev_llm_run` in config.toml, and the
first-500 checks rescore the finished runs named in the [first500] section with `mutmech score`'s code
(skipped when that section is missing). Exit status 0 when every check passes.
"""
import csv, hashlib, json, os, sys

from . import config, gold, routing, routing_v1, score, skempi

EXPECTED = {
    'keyword rule, dev, view C': (323, 511),
    'SKEMPI join, records matched': (1119, 1133),
    'routing v1, dev, view C': (416, 511),
    'first 500 mechanism answers, SHA-256': 'ee89e89b285fdcf3a4a906dbe7fff5940da7bd72f97175584378406d1aac7423',
    # https://cdn.jsdelivr.net/npm/3dmol@2.5.3/build/3Dmol-min.js, downloaded 2026-11-11 for the GUI's structure view
    'vendored 3Dmol.js 2.5.3, SHA-256': 'bcf422137a34b4e206413a8a83a67c24a1ace84e282bf3b164f6bda6aeb42a20',
}
FIRST500 = {
    'first 500, statement rules': (395, 500),
    'first 500, rules v4 extractor only': (383, 500),
    'first 500, single-agent baseline': (359, 500),
    'first 500, hybrid from the baseline': (412, 500),
    'first 500, routing no-cue by LLM from the baseline': (419, 500),
}


def main():
    g, inp = gold.load_gold()
    dev = routing.read_split('dev')
    scored = [i for i in dev if g[i]['state'] != 'unscorable']
    got = {'keyword rule, dev, view C': (sum(routing.right(g[i], gold.keyword(inp[i]['Quote'])) for i in scored), len(scored))}

    skempi.main()
    rows = list(csv.DictReader(open(skempi.OUT, encoding='utf-8')))
    got['SKEMPI join, records matched'] = (sum(r['matched'] == '1' for r in rows), len(rows))

    llm = routing.read_llm(config.DEV_LLM_RUN)
    st = routing.Structure()
    S = {i: (st.contacts(inp[i]) if routing.route_of(inp[i]['Quote']) in 'BCD' else None) for i in dev}
    sk = routing_v1.load_skempi()
    labels = {i: routing_v1.assemble(inp[i], llm.get(i), S[i], sk.get(i), 1.0)['labels'] for i in dev}
    got['routing v1, dev, view C'] = (sum(routing.right(g[i], labels[i]) for i in scored), len(scored))

    rows = [r for r in csv.DictReader(open(config.INPUT_CSV, encoding='utf-8-sig')) if g[r['ID'].strip()]['state'] == 'mechanism'][:500]
    ans = [{'ID': r['ID'], 'mapped_codes': g[r['ID'].strip()]['G'], 'mechanism_raw': g[r['ID'].strip()]['raw']} for r in rows]
    got['first 500 mechanism answers, SHA-256'] = hashlib.sha256(json.dumps(ans, ensure_ascii=False, indent=1).encode('utf-8')).hexdigest()

    vendor = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web', 'vendor', '3Dmol-min.js')
    got['vendored 3Dmol.js 2.5.3, SHA-256'] = hashlib.sha256(open(vendor, 'rb').read()).hexdigest() if os.path.exists(vendor) else 'missing'

    F = config.FIRST500
    if all(F.get(k) for k in ('answers', 'inputs', 'baseline_run', 'stmt_run', 'v4norev_run')):
        c = score.compute(F['stmt_run'], 'stmt', F['answers'], F['inputs'], F['baseline_run'])
        right = lambda n: (sum(c['ok'][n].values()), len(c['ids']))
        got.update({'first 500, statement rules': right('stmt'), 'first 500, single-agent baseline': right('baseline'),
                    'first 500, hybrid from the baseline': right('hybrid (baseline)'),
                    'first 500, routing no-cue by LLM from the baseline': right('routing no-cue by LLM (baseline)')})
        c = score.compute(F['v4norev_run'], 'v4-norev', F['answers'], F['inputs'], F['baseline_run'], c['structure'])
        got['first 500, rules v4 extractor only'] = (sum(c['ok']['v4-norev'].values()), len(c['ids']))
        EXPECTED.update(FIRST500)
    else:
        print('SKIP  first-500 checks: the [first500] section of config.toml is incomplete')

    ok = True
    for k, exp in EXPECTED.items():
        res = got[k]
        passed = res == exp
        ok &= passed
        show = (lambda v: f'{v[0]}/{v[1]}') if isinstance(exp, tuple) else (lambda v: v[:16] + '…')
        print(f"{'PASS' if passed else 'FAIL'}  {k}: got {show(res)}, expected {show(exp)}")
    sys.exit(0 if ok else 1)
