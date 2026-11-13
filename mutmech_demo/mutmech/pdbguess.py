"""Propose the PDB entry a paper PDF is about, with no LLM call and no network, then rank by structure evidence.

Sources of candidates:
  text        four-character IDs written near PDB, Protein Data Bank, accession, code, entry, coordinates or
              deposited (an ID needs a leading digit 1-9 and at least one letter, so years and counts drop out)
  dataset     the PDF's file name matches a Citation in the input CSV (the dataset's own table), or the file
              name starts with an entry of the numbering map or the structure cache (the dataset's own naming)
  cache title an entry in the local structure cache whose mmCIF title and entity names are largely covered by the
              paper's first page (title and abstract), words weighted by rarity across the cache
Ranking: for each candidate in the cache, the paper's mutations are placed with the numbering map's offsets, plus a
per-chain offset inferred when one offset clearly explains most wild types; the number of wild types that match the
structure decides, then the number of sources, then text mentions. Candidates not in the cache cannot be checked.
"""
import collections, csv, io, json, math, os, re

from . import config, findmut

KEY = re.compile(r'\b(?:PDB|Protein Data Bank|accession|codes?|entry|entries|coordinates|deposited|ID)\b', re.I)
PDB_ID = re.compile(r'(?<![A-Za-z0-9])([1-9][A-Za-z0-9]{3})(?![A-Za-z0-9])')
STOP = {'protein', 'proteins', 'structure', 'structures', 'crystal', 'complex', 'complexes', 'chain', 'chains', 'domain',
        'human', 'binding', 'between', 'their', 'which', 'these', 'those', 'resolution', 'analysis', 'factor', 'fragment',
        'mutant', 'mutants', 'residues', 'interface', 'interaction', 'interactions', 'energy', 'affinity', 'department',
        'university', 'journal', 'molecular', 'biology', 'received', 'accepted', 'research', 'article', 'using', 'during',
        'water', 'bound', 'molecule', 'molecules', 'light', 'heavy', 'single', 'variant', 'mutation', 'mutations'}
INDEX = os.path.join(config.RUNS, 'cache', 'cif_titles.json')


def text_ids(texts):
    found = collections.Counter()
    for t in texts:
        flat = ' '.join(t.split())
        for m in PDB_ID.finditer(flat):
            tok = m.group(1)
            if tok.isdigit() or not re.search(r'[A-Za-z]', tok) or re.fullmatch(r'\d+(?:st|nd|rd|th|s)', tok, re.I):
                continue
            if KEY.search(flat[max(0, m.start() - 60):m.start()]) or KEY.search(flat[m.end():m.end() + 25]):
                found[tok.upper()] += 1
    return found


def dataset_ids(pdf):
    name = os.path.basename(pdf).lower()
    out = set()
    try:
        for r in csv.DictReader(open(config.INPUT_CSV, encoding='utf-8-sig')):
            cites = re.split(r'-{2,}|\t', r.get('Citation') or '')
            if any(c.strip(' -').lower() == name for c in cites) and r.get('PDB'):
                out.add((r['PDB'].strip()[:4].upper(), 'dataset citation'))
    except OSError:
        pass
    m = re.match(r'([1-9][a-z0-9]{3})[-_ .]', name)
    if m:
        tok = m.group(1).upper()
        if tok in findmut.structure().cifs or findmut.chain_rows(tok):
            out.add((tok, 'file name'))
    return out


def words(text):
    return {w for w in re.findall(r'[a-z][a-z0-9-]{4,}', text.lower()) if w not in STOP}


def title_index():
    """mmCIF title and entity names per cached entry, from the header only, cached in runs/cache by file mtime."""
    from Bio.PDB.MMCIF2Dict import MMCIF2Dict
    old = json.load(open(INDEX, encoding='utf-8')) if os.path.exists(INDEX) else {}
    out = {}
    for code, path in findmut.structure().cifs.items():
        stamp = os.path.getmtime(path)
        if code in old and old[code]['mtime'] == stamp:
            out[code] = old[code]
            continue
        head = open(path, encoding='utf-8', errors='replace').read().split('_atom_site.', 1)[0]
        head = head[:head.rfind('loop_')] if head.rstrip().endswith('loop_') else head
        try:
            d = MMCIF2Dict(io.StringIO(head))
        except Exception:  # a header the parser cannot read only costs this source for this entry
            d = {}
        names = d.get('_struct.title', []) + d.get('_entity.pdbx_description', [])
        out[code] = {'mtime': stamp, 'text': ' '.join(n for n in names if n not in ('?', '.'))}
    if out != old:
        os.makedirs(os.path.dirname(INDEX), exist_ok=True)
        json.dump(out, open(INDEX, 'w', encoding='utf-8'))
    return out


def cache_ids(texts, k=3):
    idx = title_index()
    df = collections.Counter(w for v in idx.values() for w in words(v['text']))
    paper = words(' '.join(texts[:1])[:4000])
    score = {}
    idf = lambda w: math.log((1 + len(idx)) / (1 + df[w]))
    for code, v in idx.items():
        own = words(v['text'])
        shared = paper & own
        if len(shared) >= 2:
            frac = sum(map(idf, shared)) / sum(map(idf, own))  # share of the entry's naming the paper covers
            if frac >= 0.3:
                score[code] = (frac, sorted(shared))
    return sorted(score.items(), key=lambda x: -x[1][0])[:k]


def offsets_and_matches(code, keys):
    """Per-chain offsets (map, else inferred when clear) and the number of mutations whose wild type matches."""
    st = findmut.structure()
    model = st.model(code)[0]
    rows = findmut.chain_rows(code)
    seq = {c.id: {r.id[1]: st.seq1(r.get_resname()) for r in c if r.id[0] == ' '} for c in model}
    chains, inferred = [], {}
    for c, aa in seq.items():
        prot, off = rows.get(c, ('', None))
        src = 'numbering map' if off is not None else None
        if off is None and keys:
            votes = collections.Counter(n - num for wt, num, _ in keys for n, a in aa.items() if a == wt)
            best = votes.most_common(2)
            if best and best[0][1] >= max(3, len(keys) // 2) and (len(best) == 1 or best[0][1] >= 2 * best[1][1]):
                off, src = best[0][0], 'inferred'
                inferred[c] = off
        chains.append({'chain': c, 'protein': prot, 'offset': off or 0, 'offset_source': src or 'none, 0 assumed'})
    hit = sum(1 for wt, num, _ in keys if any(seq[c['chain']].get(num + c['offset']) == wt for c in chains))
    return chains, inferred, hit


def propose(pdf, texts, keys):
    cands = collections.defaultdict(lambda: {'sources': set(), 'mentions': 0, 'note': ''})
    for code, n in text_ids(texts).items():
        cands[code]['sources'].add('text')
        cands[code]['mentions'] = n
    for code, src in dataset_ids(pdf):
        cands[code]['sources'].add(src)
    for code, (s, shared) in cache_ids(texts):
        cands[code]['sources'].add('cache title')
        cands[code]['note'] = f"shares {', '.join(shared[:6])}"
    out = []
    cifs = findmut.structure().cifs
    for code, c in cands.items():
        row = {'pdb': code, 'sources': sorted(c['sources']), 'mentions': c['mentions'], 'note': c['note'], 'in_cache': code in cifs,
               'matched': None, 'total': len(keys), 'chains': [], 'offsets': {}}
        if code in cifs:
            row['chains'], row['offsets'], row['matched'] = offsets_and_matches(code, keys)
        row['evidence'] = (f"{row['matched']}/{len(keys)} wild types match" if row['matched'] is not None
                           else 'not in the structure cache, not checked')
        out.append(row)
    out.sort(key=lambda r: (-(r['matched'] if r['matched'] is not None else -1), -len(r['sources']), -r['mentions'], r['pdb']))
    return out


def paper(pdf, pdb=''):
    """The paper's PDB candidates and its mutations placed on the given entry, or on the best candidate."""
    texts = findmut.read(pdf)
    keys = list(findmut.grouped(texts))
    cands = propose(pdf, texts, keys)
    chosen, how = (pdb.strip().upper(), 'given') if pdb and pdb.strip() else ((cands[0]['pdb'], 'best candidate') if cands else ('', 'none found'))
    offs = next((c['offsets'] for c in cands if c['pdb'] == chosen), {})
    return {'pdb': chosen, 'chosen_by': how, 'pdb_candidates': cands, 'mutations': findmut.find(pdf, chosen, texts, offs)}


def table(cands):
    rows = [f"{'#':>3}  {'PDB':<5} {'evidence':<38} {'sources':<36} chains"]
    for i, c in enumerate(cands, 1):
        ch = '; '.join(f"{x['chain']} {x['protein'] or '?'}" + (f" (+{x['offset']} {x['offset_source']})" if x['offset'] else '') for x in c['chains'])
        rows.append(f"{i:>3}  {c['pdb']:<5} {c['evidence']:<38} {', '.join(c['sources']):<36} {ch}")
    return '\n'.join(rows)
