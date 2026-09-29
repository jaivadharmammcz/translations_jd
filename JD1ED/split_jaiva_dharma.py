#!/usr/bin/env python3
"""
Rozdělí PDF knihy (Jaiva-dharma, GVP 2013) na kapitoly v Markdownu.

Co skript dělá:
  1. vytáhne text z PDF (pdftotext -layout),
  2. převede staré kódování fontů (ä -> ā, ç -> ś, å -> ṛ ...) na Unicode IAST,
  3. odstraní záhlaví a čísla stran, spojí řádky do odstavců,
  4. označí sanskritské verše (tučně) a rozdělí knihu na kapitoly,
  5. vytvoří složku en/ (anglický text) a cs/ (prázdné kostry se stejnými
     značkami odstavců <!-- p001 --> pro tvůj překlad).

Použití:
    python3 split_jaiva_dharma.py Jaiva-dharma-5Ed-2013.pdf [vystupni_slozka]

Požadavky: Python 3.8+, poppler (příkaz pdftotext).
    macOS:   brew install poppler
    Linux:   sudo apt install poppler-utils
    Windows: stáhnout poppler a přidat do PATH
"""
import re, subprocess, sys
from pathlib import Path

MAP = {'ä':'ā','Ä':'Ā','é':'ī','É':'Ī','ü':'ū','Ü':'Ū','å':'ṛ','Å':'Ṛ','ç':'ś','Ç':'Ś',
       'ñ':'ṣ','Ñ':'Ṣ','ë':'ṇ','Ë':'Ṇ','ï':'ñ','Ï':'Ñ','ì':'ṅ','Ì':'Ṅ','ö':'ṭ','Ö':'Ṭ',
       'ò':'ḍ','Ò':'Ḍ','ù':'ḥ','Ù':'Ḥ','à':'ṁ','À':'Ṁ','è':'ṝ','í':'ḹ','ô':'ṝ',
       '\uf0b9':'•'}

def conv(s):
    return ''.join(MAP.get(c, c) for c in s)

def slug(s):
    s = conv(s).lower()
    for a, b in zip('āīūṛṝḷḹṅñṭḍṇśṣḥṁ', 'aiurrllnntdnsshm'):
        s = s.replace(a, b)
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')[:60] or 'kapitola'

# Běžící záhlaví/zápatí stránky (číslo strany + název knihy/kapitoly) vždy
# obsahuje v původním PDF odrážku U+F0B9 (soukromá oblast Unicode, pozůstatek
# fontu). Tím ho spolehlivě poznáme bez ohledu na text názvu kapitoly.
# Poznámka: funkce conv() níže převádí \uf0b9 na '•', proto musí regulární
# výraz počítat s OBĚMA variantami (před i po převodu kódování).
PAGEHEAD_RE = re.compile(r'[\uf0b9•]')
# Citace zdroje za veršem, např. „Śrī Caitanya-caritāmṛta (Madhya-līlā 8.128)“ —
# vždy začíná velkým písmenem a končí závorkou s číslem uvnitř.
CITATION_RE = re.compile(r'^[A-ZĀĪŪṚŚṢṆṬḌṄÑḤṀ].*\([^()]*\d[^()]*\)\s*$')
CHAP_RE     = re.compile(r'^\s*C\s*haptEr\s+(\d+)\s*$', re.I)
ENDS_RE     = re.compile(r'T\s*HuS\s+ENDS', re.I)

def indent(l):
    return len(l) - len(l.lstrip(' '))

def page_to_blocks(page):
    """Vrátí seznam (typ, text) pro jednu stránku: 'p' odstavec, 'v' řádek
    verše, 'c' citace zdroje.

    Řádky se nejdřív rozdělí na skupiny podle PRÁZDNÝCH ŘÁDKŮ v originále —
    to je spolehlivá hranice mezi bloky (odstavec/verš/citace). Uvnitř
    skupiny se pak odsazení každého řádku poměřuje vůči nejmenšímu odsazení
    UVNITŘ TÉTO SKUPINY (ne vůči celé stránce), protože verš a jeho překlad
    v knize často leží v jedné skupině bez prázdného řádku mezi sebou, a
    odsazení překladu (stejné na každém řádku) by jinak zkreslilo odhad.
    """
    raw_lines = [l.rstrip() for l in page.split('\n')]
    raw_lines = [l for l in raw_lines if not PAGEHEAD_RE.search(l)]
    raw_lines = [l for l in raw_lines if not re.fullmatch(r'\s*\d{1,4}\s*', l)]

    groups, cur = [], []
    for l in raw_lines:
        if l.strip():
            cur.append(l)
        elif cur:
            groups.append(cur); cur = []
    if cur:
        groups.append(cur)
    if not groups:
        return []

    out = []
    for g in groups:
        base = min(indent(l) for l in g)
        for l in g:
            d = indent(l) - base
            t = l.strip()
            if d >= 6:
                if CITATION_RE.match(t):
                    out.append(('c', t))       # citace zdroje za veršem
                else:
                    out.append(('v', t))
            elif d >= 2:
                out.append(('new', t))         # začátek odstavce
            else:
                out.append(('cont', t))
    return out

def join(prev, nxt):
    if prev.endswith('-'):
        return prev + nxt
    return prev + ' ' + nxt

def build_chapter(pages):
    """pages = seznam textů stránek jedné kapitoly -> seznam odstavců Markdownu."""
    paras = []          # (typ, text)
    for page in pages:
        for kind, t in page_to_blocks(page):
            if kind == 'v':
                if paras and paras[-1][0] == 'v':
                    paras[-1] = ('v', paras[-1][1] + [t])
                else:
                    paras.append(('v', [t]))
            elif kind == 'c':
                paras.append(('c', t))
            elif kind == 'new' or not paras or paras[-1][0] in ('v', 'c'):
                # odstavec hned po verši/citaci = překlad verše -> vystředit
                ptype = 'pt' if paras and paras[-1][0] in ('v', 'c') else 'p'
                paras.append((ptype, t))
            else:
                paras.append((paras[-1][0], join(paras[-1][1], t)))
                del paras[-2]
    md = []
    for kind, t in paras:
        if kind == 'v':
            md.append('<center>\n\n' + '  \n'.join(f'<code style="color:#000000;">{x}</code>' for x in t) + '\n\n</center>')
        elif kind == 'c':
            md.append(f'<p style="text-align:center;font-size:0.85em;color:#000000;">{t}</p>')
        elif kind == 'pt':
            md.append(f'<p style="text-align:center;">{t}</p>')
        else:
            md.append(t)
    return md

def fix_dropcap(text):
    # "Ś    rī Harihara" -> "Śrī Harihara" (iniciála oddělená mezerami)
    return re.sub(r'^(\S)\s{3,}(\S)', r'\1\2', text, count=1, flags=re.M)

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    pdf = sys.argv[1]
    out = Path(sys.argv[2] if len(sys.argv) > 2 else 'jaiva-dharma')
    raw = subprocess.run(['pdftotext', '-layout', pdf, '-'], capture_output=True,
                         text=True, check=True).stdout
    pages = [conv(p) for p in raw.split('\f')]

    # najdi první stránky kapitol (obsah na začátku knihy je také "Chapter N",
    # proto pro každé číslo bereme POSLEDNÍ výskyt, tj. skutečný začátek kapitoly)
    found = {}
    for i, p in enumerate(pages):
        lines = p.split('\n')
        idx = next((q for q, l in enumerate(lines) if l.strip()), None)
        if idx is None:
            continue
        m = CHAP_RE.match(lines[idx])
        if not m:
            continue
        title_parts, started = [], False
        for l in lines[idx + 1:idx + 10]:
            if l.strip():
                title_parts.append(l.strip()); started = True
            elif started:
                break
        title = re.sub(r'\s+', ' ', ' '.join(title_parts))
        found[int(m.group(1))] = (i, title)
    starts = sorted(((n, i, t) for n, (i, t) in found.items()), key=lambda x: x[1])
    if not starts:
        sys.exit('Nenašel jsem žádné kapitoly – zkontroluj PDF.')

    for sub in ('en', 'cs'):
        (out / sub).mkdir(parents=True, exist_ok=True)

    def save(name, title, paras, is_chapter=True):
        head_style = 'text-align:center;font-weight:bold;color:#000000;'
        en = [f'<p style="{head_style}">{title}</p>', '']
        cs = [f'<p style="{head_style}">{title}</p>  <!-- přeložit nadpis -->', '']
        for k, p in enumerate(paras, 1):
            tag = f'<!-- p{k:03d} -->'
            en += [tag, p, '']
            cs += [tag, '', '']
        (out / 'en' / f'{name}.md').write_text('\n'.join(en), encoding='utf-8')
        (out / 'cs' / f'{name}.md').write_text('\n'.join(cs), encoding='utf-8')

    # úvodní část (před kapitolou 1)
    front = [p for p in pages[:starts[0][1]]]
    save('00-uvod', 'Úvodní části (Front matter)',
         [x for pg in front for x in build_chapter([pg])])

    # kapitoly
    for k, (n, i, title) in enumerate(starts):
        end = starts[k + 1][1] if k + 1 < len(starts) else None
        if end is None:   # poslední kapitola: končí stránkou s formulí „Thus ends…“
            end = next((j + 1 for j in range(i, len(pages)) if ENDS_RE.search(pages[j])), i + 60)
        chunk = pages[i:end]
        text_pages = []
        for j, pg in enumerate(chunk):
            if j == 0:
                # odstraň nadpis kapitoly (2 první neprázdné řádky)
                ls = pg.split('\n'); new = []; state = 0
                for l in ls:
                    if state == 0 and l.strip():
                        state = 1; continue          # řádek "Chapter N"
                    if state == 1:
                        if l.strip():
                            continue                 # řádky nadpisu
                        state = 2
                    new.append(l)
                pg = fix_dropcap('\n'.join(new))
            text_pages.append(pg)
        paras = build_chapter(text_pages)
        # odstraň závěrečnou formuli kapitoly a vše za ní (poznámky ke kapitole)
        cut = next((q for q, p in enumerate(paras) if ENDS_RE.search(p)), None)
        if cut is not None:
            paras = paras[:cut]
        name = f'{n:02d}-{slug(title)}'
        save(name, f'Chapter {n} – {title}', paras)
        print(f'kapitola {n:2d}: {len(paras):4d} odstavců  ->  {name}.md')

    (out / 'glossary.md').write_text(
        '# Slovník\n\n| Termín | Česky | Poznámka |\n|---|---|---|\n', encoding='utf-8')
    print(f'\nHotovo. Výstup: {out.resolve()}')

if __name__ == '__main__':
    main()
