"""Put every dialogue turn ("Name: ...") on its own paragraph with the speaker name in bold.

Keeps <!-- pNNN --> markers untouched (en/cs alignment); new paragraphs are added inside a chunk.
Usage: python3 speakers.py [--dry] files...
"""
import re, sys

SPEAKERS = ['Vijaya', 'Gosvāmī', 'Gosvamī', 'Bābājī', 'Vrajanātha', 'Vaiṣṇava dāsa', 'Digambara', 'Advaita',
            'Nityānanda dāsa', 'Lāhirī', 'Ananta dāsa', 'Yādava dāsa', 'Cūḍāmaṇi', 'Nyāyaratna', 'Devīdāsa',
            'Gorācānda', 'Mullah', 'Kāzī', 'Caṇḍīdāsa']
ALT = '|'.join(sorted(map(re.escape, SPEAKERS), key=len, reverse=True))
# label not glued to a preceding word char, not preceded by a capitalised name ("Rūpa Gosvāmī:"),
# followed by a space (not a newline — "…composed by Caṇḍīdāsa:\n<verse>" is not dialogue)
LABEL = re.compile(r'(?<![\w\-*])(%s):(?: (?=\S)|\s*$)' % ALT)
PREV_WORD = re.compile(r'(\S+)\s$')

def is_turn(text, m):
    before = text[:m.start()]
    if not before.strip() or before.endswith('>'):
        return True
    pw = PREV_WORD.search(before[-40:])
    if not pw:
        return True
    w = pw.group(1)
    if re.search(r'[.!?”"’‘“)…]\d*$', w):      # sentence end, optionally a footnote number
        return True
    if not text[m.end():].strip():                # label right before a verse: only after a sentence end
        return False
    return w[0].islower()                         # missing full stop ("… gauṇa Vijaya:")

def split_chunk(chunk):
    body = chunk.strip('\n')
    if not body or '<center>' in body:
        return chunk
    m_p = re.match(r'^(<p\s[^>]*>)([\s\S]*)</p>$', body)
    open_tag, inner = (m_p.group(1), m_p.group(2)) if m_p else ('', body)
    cuts = [m for m in LABEL.finditer(inner) if is_turn(inner, m)]
    if not cuts:
        return chunk
    parts = []
    head = inner[:cuts[0].start()].rstrip()
    if head:
        parts.append(f'{open_tag}{head}</p>' if open_tag else head)
    for i, m in enumerate(cuts):
        end = cuts[i + 1].start() if i + 1 < len(cuts) else len(inner)
        parts.append((f'**{m.group(1)}:** ' + inner[m.end():end].strip()).rstrip())
    lead = chunk[:len(chunk) - len(chunk.lstrip('\n'))]
    trail = chunk[len(chunk.rstrip('\n')):]
    return lead + '\n\n'.join(parts) + trail

def process(text):
    pieces = re.split(r'(<!--\s*p\d+\s*-->)', text)
    return ''.join(p if re.fullmatch(r'<!--\s*p\d+\s*-->', p) else split_chunk(p) for p in pieces)

if __name__ == '__main__':
    dry = '--dry' in sys.argv
    total = 0
    for f in [a for a in sys.argv[1:] if a != '--dry']:
        t = open(f, encoding='utf-8').read()
        n = process(t)
        cnt = n.count('**') // 2 - t.count('**') // 2
        total += cnt
        if n != t:
            print(f'{cnt:4d}  {f}')
            if not dry:
                open(f, 'w', encoding='utf-8').write(n)
    print('total turns:', total)
