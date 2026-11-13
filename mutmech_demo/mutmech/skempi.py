#!/usr/bin/env python3
"""Join MutMech records to SKEMPI 2.0 single mutations. Uses no curator labels, so it covers every split.

Match: PDB entry from the record's PDB cell + 'Mutation DECODED' parsed as wild type, chain, number, mutant,
against SKEMPI's '#Pdb' entry code and 'Mutation(s)_PDB' (wild type, chain, PDB number, mutant), single
mutations only. Several SKEMPI rows for one mutation (repeat measurements) are summarised by their median.
ddG = R T ln(Kd_mut / Kd_wt) in kcal/mol with R = 1.9872e-3 kcal/(mol K) and T from SKEMPI's Temperature
(298 K when it has no number). Kinetics: log10(kon_mut / kon_wt) and log10(koff_mut / koff_wt).

Usage: python3 -I eval/skempi/join_skempi.py   (writes eval/skempi/mutmech_skempi.csv)
"""
import collections, csv, hashlib, math, os, re, statistics, sys

from . import config
from . import routing as R  # PDB-cell and mutation parsing, same as the structure check
from . import gold as sg  # input records only; labels are not read

SKEMPI = config.SKEMPI_CSV
OUT = os.path.join(config.RUNS, 'skempi', 'mutmech_skempi.csv')
RGAS = 1.9872e-3


def num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v > 0 and math.isfinite(v) else None


def load_skempi():
    rows = collections.defaultdict(list)
    for row in csv.DictReader(open(SKEMPI, encoding='utf-8', errors='replace'), delimiter=';'):
        muts = [m.strip() for m in row['Mutation(s)_PDB'].split(',')]
        if len(muts) != 1:
            continue
        t = re.match(r'\s*(\d+(?:\.\d+)?)', row['Temperature'] or '')
        T = float(t.group(1)) if t else 298.0
        km, kw = num(row['Affinity_mut_parsed']), num(row['Affinity_wt_parsed'])
        onm, onw = num(row['kon_mut_parsed']), num(row['kon_wt_parsed'])
        offm, offw = num(row['koff_mut_parsed']), num(row['koff_wt_parsed'])
        rows[(row['#Pdb'][:4].upper(), muts[0])].append({
            'complex': row['#Pdb'], 'ddg': RGAS * T * math.log(km / kw) if km and kw else None,
            'bound': any(c in (row['Affinity_mut (M)'] or '') for c in '<>'),
            'dkon': math.log10(onm / onw) if onm and onw else None,
            'dkoff': math.log10(offm / offw) if offm and offw else None,
            'location': row['iMutation_Location(s)'], 'method': row['Method'], 'reference': row['Reference'], 'T': T})
    return rows


def med(vals):
    vals = [v for v in vals if v is not None]
    return round(statistics.median(vals), 3) if vals else ''


def main():
    sk = load_skempi()
    _, inp = sg.load_gold()
    cols = ['ID', 'matched', 'skempi_complex', 'skempi_mutation', 'n_measurements', 'ddg_median_kcal', 'ddg_min_kcal',
            'ddg_max_kcal', 'affinity_is_bound', 'dlog10_kon_median', 'dlog10_koff_median', 'location', 'methods', 'references']
    n = 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i, r in inp.items():
            mu = R.Structure.mutation(r['Mutation DECODED'])
            hit, key = None, ''
            if mu and mu[3]:
                for t in R.Structure.pdb_tokens(r['PDB']):
                    key = f'{mu[0]}{mu[3]}{mu[1]}{mu[2]}'
                    hit = sk.get((t, key))
                    if hit:
                        break
            if not hit:
                w.writerow([i, 0] + [''] * (len(cols) - 2))
                continue
            n += 1
            d = [x['ddg'] for x in hit if x['ddg'] is not None]
            w.writerow([i, 1, hit[0]['complex'], key, len(hit), med(d), round(min(d), 3) if d else '', round(max(d), 3) if d else '',
                        int(any(x['bound'] for x in hit)), med(x['dkon'] for x in hit), med(x['dkoff'] for x in hit),
                        ';'.join(sorted({x['location'] for x in hit})), ';'.join(sorted({x['method'] for x in hit})),
                        ';'.join(sorted({x['reference'] for x in hit}))])
    print(f'{n} of {len(inp)} records matched; SKEMPI sha256 {hashlib.sha256(open(SKEMPI, "rb").read()).hexdigest()}; wrote {OUT}')


if __name__ == '__main__':
    main()
