"""Find the mutations a paper PDF mentions, with no LLM call, and propose their PDB numbering.

Forms recognised in the PDF's text layer:
  one-letter      R64A, D164A, E174A (a figure or table label such as "Fig. S1A" is skipped)
  three-letter    Arg64Ala, Arg-64-Ala, Arg64→Ala, Arg64->Ala
  phrase          "R64 to alanine", "mutation of Arg64 to Ala", "Arg64 was replaced by alanine"
  alanine scan    "alanine substitution of Arg64", "Ala mutation at R64", one residue only, not a list
Hits are grouped by wild type, paper number and mutant, with the count, the pages, the forms as written and up
to three context sentences. When a PDB entry is given, each candidate is placed on a chain with the numbering
map's offset for that chain (0 where the map gives none) and its wild type is checked against the cached
structure: "wild type matches structure", "mismatch" or "not checked". The text's attribution to a protein is
taken from the protein names in the numbering map, when one chain's name words appear near the mention and the
others' do not. Ranking: structure matches first, then by count, then by first page.
"""
import collections, csv, functools, re

from . import config, pdftext, routing

ONE = 'ACDEFGHIKLMNPQRSTVWY'
THREE = pdftext.THREE
BY_THREE = {v.lower(): k for k, v in THREE.items()}
FULL = {'alanine': 'A', 'arginine': 'R', 'asparagine': 'N', 'aspartate': 'D', 'aspartic acid': 'D', 'cysteine': 'C',
        'glutamine': 'Q', 'glutamate': 'E', 'glutamic acid': 'E', 'glycine': 'G', 'histidine': 'H', 'isoleucine': 'I',
        'leucine': 'L', 'lysine': 'K', 'methionine': 'M', 'phenylalanine': 'F', 'proline': 'P', 'serine': 'S',
        'threonine': 'T', 'tryptophan': 'W', 'tyrosine': 'Y', 'valine': 'V'}
T3 = '|'.join(v for v in THREE.values())
FN = '|'.join(sorted(FULL, key=len, reverse=True))
RES = rf'(?:(?P<w3>{T3})|(?P<w1>[{ONE}]))[- ]?(?P<n>\d{{1,4}})'
PATTERNS = [
    ('one-letter', re.compile(rf'(?<![A-Za-z0-9])(?P<w1>[{ONE}])(?P<n>\d{{1,4}})(?P<m1>[{ONE}])(?![A-Za-z0-9])')),
    ('three-letter', re.compile(rf'(?<![A-Za-z])(?P<w3>{T3})[- ]?(?P<n>\d{{1,4}})(?:-|\s*(?:→|->|⟶|>)\s*)?(?P<m3>{T3})(?![A-Za-z0-9])')),
    ('phrase', re.compile(rf'(?<![A-Za-z0-9]){RES}(?![0-9])\s*(?i:(?:(?:was|were|is|are)\s+)?(?:(?:mutated|replaced|substituted|changed|converted)'
                          rf'\s+(?:to|into|by|with)|to|→|->)\s+(?:an?\s+)?)(?:(?P<mf>(?i:{FN}))\b|(?P<m3>{T3})(?![A-Za-z0-9]))')),
    ('alanine scan', re.compile(rf'\b(?:alanine|Ala)[- ](?:substitution|mutation|replacement|mutant)s?\s+(?:of|at|for)\s+'
                                rf'(?:(?:hGH|the|residue)\s+)?{RES}(?![0-9])(?!\s*(?:,|and|or)\s*(?:[A-Z][a-z]{{2}}|[A-Z])-?\d)')),
]
LABEL_BEFORE = re.compile(r'(?:Fig(?:ure)?s?\.?|Table|Panel|Supplementary|Movie|Eq(?:uation)?\.?)\s*$', re.I)


def code(m, one, three, full=None):
    g = m.groupdict()
    if g.get(one):
        return g[one].upper() if len(g[one]) == 1 else None
    if g.get(three):
        return BY_THREE.get(g[three].lower())
    if full and g.get(full):
        return FULL.get(g[full].lower())
    return None


def hits(page_texts):
    for pi, text in enumerate(page_texts):
        sents = pdftext.sentences(text)
        for si, s in enumerate(sents):
            before = (sents[si - 1][-16:] + ' ') if si else ''
            seen = set()
            for form, rx in PATTERNS:
                for m in rx.finditer(s):
                    wt, mut, n = code(m, 'w1', 'w3'), code(m, 'm1', 'm3', 'mf'), int(m.group('n'))
                    if form == 'alanine scan':
                        mut = 'A'
                    if not wt or not mut or wt == mut or not 1 <= n <= 2500 or m.start('n') in seen:
                        continue
                    if form == 'one-letter' and LABEL_BEFORE.search((before + s[:m.start()])[-16:]):
                        continue
                    seen.add(m.start('n'))
                    yield {'key': (wt, n, mut), 'page': pi + 1, 'sentence': si, 'form': form, 'written': m.group(0), 'text': s}


@functools.lru_cache(maxsize=1)
def structure():
    """One structure index per process: the cif cache scan and parsed models are shared."""
    return routing.Structure()


def chain_rows(pdb):
    """Numbering-map rows for this entry: chain -> (protein, offset or None)."""
    out = {}
    try:
        for r in csv.DictReader(open(config.NUMBERING_MAP, encoding='utf-8-sig')):
            if r['PDB'].upper() == pdb.upper():
                off = re.findall(r'-?\d+', r['pdb_minus_paper'] or '')
                out.setdefault(r['chain'], (r['protein'], int(off[0]) if len(off) == 1 else None))
    except (OSError, KeyError):
        pass
    return out


def name_words(chains):
    """Words of each chain's protein name that no other chain's name has (e.g. RECEPTOR)."""
    words = {c: {w.lower() for w in re.findall(r'[A-Za-z]{4,}', p)} for c, (p, _) in chains.items()}
    return {c: w - set().union(*(words[o] for o in words if o != c)) for c, w in words.items()}


class Placer:
    """offsets: chain -> pdb_minus_paper inferred elsewhere, used only where the numbering map gives none."""
    def __init__(self, pdb, offsets=None):
        self.pdb = (pdb or '').upper()
        self.chains = chain_rows(self.pdb) if self.pdb else {}
        self.model = None
        if self.pdb:
            st = structure()
            if self.pdb in st.cifs:
                self.st, self.model = st, st.model(self.pdb)[0]
                for c in self.model:
                    self.chains.setdefault(c.id, ('', None))
        for c, off in (offsets or {}).items():
            if c in self.chains and self.chains[c][1] is None:
                self.chains[c] = (self.chains[c][0], off)
        self.words = name_words(self.chains)

    def attributed(self, texts):
        score = {c: sum(len(re.findall(rf'\b{w}', t, re.I)) for w in ws for t in texts) for c, ws in self.words.items() if ws}
        hit = [c for c, n in score.items() if n]
        if len(hit) == 1:
            return hit[0]
        if not hit and len(self.words) == 2 and sum(1 for ws in self.words.values() if ws) == 1:
            return next(c for c, ws in self.words.items() if not ws)  # the only other chain, e.g. the hormone
        return None

    def place(self, wt, n, mut, texts):
        if not self.pdb:
            return {'pdb_mutation': f'{wt}{n}{mut}', 'chain': '', 'protein': '', 'structure': 'not checked', 'attributed_chain': None}
        said = self.attributed(texts)
        options = []
        for c, (prot, off) in self.chains.items():
            pn = n + (off or 0)
            state = 'not checked'
            if self.model is not None:
                res = self.model[c][(' ', pn, ' ')] if c in self.model and (' ', pn, ' ') in self.model[c] else None
                state = ('wild type matches structure' if res is not None and self.st.seq1(res.get_resname()) == wt else 'mismatch')
            options.append((state == 'wild type matches structure', c == said, off is not None, c, pn, prot, state))
        if not options:
            return {'pdb_mutation': f'{wt}{n}{mut}', 'chain': '', 'protein': '', 'structure': 'not checked', 'attributed_chain': said}
        best = max(options, key=lambda o: (o[0] and o[1], o[0] and o[2], o[0], o[1]))
        ambiguous = best[0] and not best[1] and sum(o[0] for o in options) > 1
        return {'pdb_mutation': f'{wt}{best[4]}{mut}', 'chain': best[3], 'protein': best[5], 'structure': best[6],
                'attributed_chain': said, 'ambiguous_chain': ambiguous}


def read(pdf):
    texts = pdftext.pages(pdf)
    if sum(len(t.strip()) for t in texts) < 200:
        raise SystemExit(f'{pdf}: no text layer found; run OCR on it first')
    return texts


def grouped(texts):
    groups = collections.OrderedDict()
    for h in hits(texts):
        groups.setdefault(h['key'], []).append(h)
    return groups


def find(pdf, pdb='', texts=None, offsets=None):
    texts = texts or read(pdf)
    groups = grouped(texts)
    placer = Placer(pdb, offsets)
    out = []
    for (wt, n, mut), hs in groups.items():
        ctx = []
        for h in hs:
            if h['text'] not in [c['text'] for c in ctx]:
                ctx.append({'page': h['page'], 'text': h['text']})
        cand = {'written': f'{wt}{n}{mut}', 'wild_type': wt, 'paper_number': n, 'mutant': mut, 'count': len(hs),
                'pages': sorted({h['page'] for h in hs}), 'forms': collections.Counter(h['written'] for h in hs).most_common(3),
                'contexts': ctx[:3]}
        cand.update(placer.place(wt, n, mut, [c['text'] for c in ctx]))
        cand['mutation'] = f"{cand['pdb_mutation']} (chain {cand['chain']})" if cand['chain'] else cand['pdb_mutation']
        out.append(cand)
    out.sort(key=lambda c: (c['structure'] != 'wild type matches structure', -c['count'], c['pages'][0], c['paper_number']))
    return out


def table(cands):
    rows = [f"{'#':>3}  {'as written':<11} {'PDB mutation':<20} {'structure':<28} {'count':>5}  pages"]
    for i, c in enumerate(cands, 1):
        rows.append(f"{i:>3}  {c['written']:<11} {c['mutation']:<20} {c['structure']:<28} {c['count']:>5}  {','.join(map(str, c['pages']))}")
    return '\n'.join(rows)
