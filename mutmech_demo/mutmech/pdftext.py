"""Find the passages of a paper PDF that discuss one mutation.

Text comes from the PDF's text layer (PyMuPDF); scanned PDFs without one need OCR first, which this
module does not do. A passage is a sentence that names the residue, with one sentence on each side.
"""
import re

import pymupdf

from . import routing

THREE = {'A': 'Ala', 'R': 'Arg', 'N': 'Asn', 'D': 'Asp', 'C': 'Cys', 'Q': 'Gln', 'E': 'Glu', 'G': 'Gly', 'H': 'His',
         'I': 'Ile', 'L': 'Leu', 'K': 'Lys', 'M': 'Met', 'F': 'Phe', 'P': 'Pro', 'S': 'Ser', 'T': 'Thr', 'W': 'Trp',
         'Y': 'Tyr', 'V': 'Val'}
MECH = re.compile('|'.join(list(routing.RX.values()) + [routing.CUE.pattern]), re.I)


def pages(pdf_path):
    with pymupdf.open(pdf_path) as doc:
        return [page.get_text('text') for page in doc]


def sentences(text):
    text = re.sub(r'-\n(?=[a-z])', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return [s for s in re.split(r'(?<=[.!?])\s+(?=[A-Z(\[])', text) if s]


def patterns(wt, num, mut):
    t, tm = THREE[wt], THREE.get(mut, mut)
    exact = re.compile(rf'(?<![A-Za-z0-9]){wt}{num}{mut}(?![0-9A-Za-z])|(?i:{t})[- ]?{num}\s*(?:→|->|to)\s*(?i:{tm})\b')
    residue = re.compile(rf'(?<![A-Za-z0-9]){wt}{num}(?![0-9])|(?i:{t})[- ]?{num}(?![0-9])')
    return exact, residue


def find_passages(page_texts, wt, numbers, mut, k=6, max_chars=4000):
    """Up to k passages that name the residue under any of the given numbers, best first by score:
    3 per exact mutation mention, 1 per residue mention, 1 if the passage names an interaction."""
    pats = [patterns(wt, n, mut) for n in numbers]
    cands = []
    for pi, text in enumerate(page_texts):
        sents = sentences(text)
        for j, s in enumerate(sents):
            ex = sum(len(e.findall(s)) for e, _ in pats)
            rs = sum(len(r.findall(s)) for _, r in pats)
            if not ex and not rs:
                continue
            window = ' '.join(sents[max(0, j - 1): j + 2])
            score = 3 * ex + rs + (1 if MECH.search(window) else 0)
            cands.append({'page': pi + 1, 'sentence': j, 'score': score, 'exact': ex > 0, 'text': window})
    cands.sort(key=lambda c: (-c['score'], c['page'], c['sentence']))
    chosen, used = [], 0
    for c in cands:
        if any(c['page'] == d['page'] and abs(c['sentence'] - d['sentence']) <= 1 for d in chosen):
            continue
        if len(chosen) >= k or used + len(c['text']) > max_chars:
            break
        chosen.append(c)
        used += len(c['text'])
    return sorted(chosen, key=lambda c: (c['page'], c['sentence']))
