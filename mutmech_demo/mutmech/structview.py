"""Site annotation of a mutation on the cached structure, for the GUI's 3D view. No LLM call, no network.

Follows the conventions of the pdb-mutation-visualizer skill: the deposited structure is shown as it is, the
mutated residue is highlighted where it sits and the mutant side chain is not modelled. The browser gets the first
model of the cached mmCIF in PDB format (author chains and numbers), the same model this module checks. A wild type
that does not match the structure is reported as a mismatch and no neighbours are listed for it.
"""
import functools, io, re

from . import findmut, routing

NOTE = 'Site annotation on the deposited structure. The mutant side chain is not modelled.'
SHELL = 4.5


structure = findmut.structure


def cif_path(pdb):
    return structure().cifs.get((pdb or '').upper())


@functools.lru_cache(maxsize=8)
def pdb_text(pdb):
    """First model in PDB format, as validated here; PDBIO fails on chains or numbers PDB format cannot hold."""
    from Bio.PDB import PDBIO
    out, w = io.StringIO(), PDBIO()
    w.set_structure(structure().model(pdb.upper())[0])
    w.save(out)
    return out.getvalue()


def residue(model, chain, num):
    return model[chain][(' ', num, ' ')] if chain in model and (' ', num, ' ') in model[chain] else None


def participants_of(statements):
    """Residues named as participants in statement-rules output: (text, chain, one-letter, paper number)."""
    seen = []
    for s in statements or []:
        for p in s.get('participants') or []:
            m = re.fullmatch(r'([A-Z][a-z]{2})-?(\d{1,4})', (p.get('residue') or '').strip())
            wt = findmut.BY_THREE.get(m.group(1).lower()) if m else None
            if wt and (p['residue'], p.get('chain') or '') not in [(x[0], x[1]) for x in seen]:
                seen.append((p['residue'], p.get('chain') or '', wt, int(m.group(2))))
    return seen


def site(pdb, mutation, paper_number=None, statements=None):
    st, code = structure(), (pdb or '').upper()
    if code not in st.cifs:
        return {'error': f'no cached structure for {code or "an empty PDB entry"}; add its mmCIF to a structure_dirs folder in config.toml'}
    model, _, seqs = st.model(code)
    rows = findmut.chain_rows(code)
    chains = [{'chain': c.id, 'protein': rows.get(c.id, ('', None))[0], 'pdb_minus_paper': rows.get(c.id, ('', None))[1],
               'residues': sum(1 for r in c if r.id[0] == ' ')} for c in model]
    out = {'pdb': code, 'mutation': mutation, 'note': NOTE, 'chains': chains, 'site': None, 'neighbours': [], 'named': [],
           'problem': None}
    mu = routing.Structure.mutation(mutation or '')
    if not mu or not mu[3]:
        out['problem'] = f'cannot place {mutation!r}: give it in PDB numbering with a chain, like "D364A (chain B)"'
        return out
    wt, num, mut, ch = mu
    res = residue(model, ch, num)
    observed = st.seq1(res.get_resname()) if res is not None else None
    paper = f' (paper {wt}{paper_number})' if paper_number not in (None, '', num) else ''
    out['site'] = {'chain': ch, 'resi': num, 'wt': wt, 'mut': mut, 'observed': res.get_resname() if res is not None else None,
                   'present': res is not None, 'matches': observed == wt, 'label': f'{ch}:{wt}{num}{paper} → {mut}'}
    if res is None:
        out['problem'] = f'chain {ch} residue {num} has no coordinates in {code}'
        return out
    if observed != wt:
        out['problem'] = (f'wild-type mismatch: the paper says {wt}{num} but {code} has {res.get_resname()} at {ch}:{num}; '
                          'the site shown is where that number falls, not a verified site')
        return out
    partners = {c for c in seqs if c != ch and seqs[c] != seqs[ch]}
    contacts = st.contacts_by_residue(code, ch, num)
    near = {}
    for a in res:
        for b in st.model(code)[1].search(a.coord, SHELL):
            r = b.get_parent()
            k = (r.get_parent().id, r.id[1], r.get_resname())
            if r is not res:
                near[k] = min(near.get(k, 99.0), float(a - b))
    out['neighbours'] = sorted(({'chain': c, 'resi': n, 'resn': rn, 'partner': c in partners, 'distance': round(d, 2),
                                 'contacts': sorted(contacts.get((c, n, rn), ()))} for (c, n, rn), d in near.items()),
                               key=lambda x: (not x['partner'], x['chain'], x['resi']))
    for text, pch, pwt, pnum in participants_of(statements):
        off = rows.get(pch, ('', None))[1] or 0
        r = residue(model, pch, pnum + off)
        hit = r is not None and st.seq1(r.get_resname()) == pwt
        if (pch, pnum + off) != (ch, num):
            out['named'].append({'text': text, 'chain': pch, 'resi': pnum + off, 'resn': r.get_resname() if r is not None else None,
                                 'matches': hit})
    return out
