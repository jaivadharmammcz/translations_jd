// Exports a translated Jaiva Dharma chapter (Markdown with HTML fragments) to output/docx and output/pdf.
// Usage (from jaiva-dharma/): node scripts/export.js cs/10-nitya-dharma-history.md [output-basename]
// Style: body Times New Roman; Sanskrit verses Palatino italic, black, centered; translations upright, centered;
// source citation smaller under the verse; **Name:** dialogue turns with the speaker in bold.
const fs = require('fs');
const path = require('path');
const os = require('os');
const { execFileSync } = require('child_process');
const docx = require('docx');
const { Document, Packer, Paragraph, TextRun, AlignmentType } = docx;

const [, , inPath, baseArg] = process.argv;
if (!inPath) { console.error('Usage: node scripts/export.js <chapter.md> [output-basename]'); process.exit(1); }
const ROOT = path.resolve(__dirname, '..');
const base = baseArg || path.basename(inPath, '.md');
fs.mkdirSync(path.join(ROOT, 'output/docx'), { recursive: true });
fs.mkdirSync(path.join(ROOT, 'output/pdf'), { recursive: true });
const docxPath = path.join(ROOT, 'output/docx', base + '.docx');
const pdfPath = path.join(ROOT, 'output/pdf', base + '.pdf');
const htmlPath = path.join(os.tmpdir(), base + '.html');
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const BODY_FONT = process.env.BODY_FONT || 'Times New Roman';
const SKT_FONT = process.env.SKT_FONT || 'Palatino';

const src = fs.readFileSync(inPath, 'utf8');

// ---------- 1. split into raw chunks at <!-- pNNN --> markers, then into paragraphs at blank lines ----------
const rawChunks = src.split(/<!--\s*p\d+\s*-->/).map(s => s.trim()).filter(Boolean)
  .flatMap(c => /<center>/.test(c) ? [c] : c.split(/\n\s*\n/).map(s => s.trim()).filter(Boolean));

const stripTags = s => s.replace(/<!--[\s\S]*?-->/g, '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
const IAST = /[āīūṛṝḷṁḥṅñṭḍṇśṣ]/;
const CZECH = /[ěščřžýáíéůúťďňóĚŠČŘŽÝÁÍÉŮÚŤĎŇÓ]/;
const isVerseWord = w => /^[a-zāīūṛṝḷṁḥṅñṭḍṇśṣ‘’'\-]+[,;]?$/.test(w) && !CZECH.test(w);

// Leading run of lowercase transliterated Sanskrit words (for verses that lost their <center>/<code> markup).
function splitLeadingVerse(text) {
  const words = text.split(' ');
  let n = 0;
  while (n < words.length && isVerseWord(words[n])) n++;
  if (n >= 3 && IAST.test(words.slice(0, n).join(' '))) {
    return [words.slice(0, n).join(' '), words.slice(n).join(' ')];
  }
  return null;
}

// ---------- 2. classify chunks ----------
const blocks = []; // {type:'title'|'verse'|'source'|'para', text|lines, centered, speaker}
for (const chunk of rawChunks) {
  if (/<center>/.test(chunk)) {
    const lines = [...chunk.matchAll(/<code[^>]*>([\s\S]*?)<\/code>/g)].map(m => m[1].trim());
    blocks.push({ type: 'verse', lines });
    continue;
  }
  // dialogue turn: **Name:** text (always its own paragraph)
  const sp = chunk.match(/^\*\*([^*]+?):\*\*\s*([\s\S]*)$/);
  if (sp) {
    blocks.push({ type: 'para', speaker: sp[1], text: stripTags(sp[2]), centered: false });
    continue;
  }
  const pMatch = chunk.match(/^<p\s+style="([^"]*)"[^>]*>([\s\S]*)<\/p>/);
  if (pMatch) {
    const style = pMatch[1], text = stripTags(pMatch[2]);
    if (/font-weight:\s*bold/.test(style) && blocks.length === 0) blocks.push({ type: 'title', text });
    else if (/font-size/.test(style)) blocks.push({ type: 'source', text });
    else blocks.push({ type: 'para', text, centered: /text-align:\s*center/.test(style) });
    continue;
  }
  const text = stripTags(chunk);
  const sv = splitLeadingVerse(text);
  if (sv) {
    blocks.push({ type: 'verse', lines: [sv[0]] });
    if (sv[1]) blocks.push({ type: 'para', text: sv[1], centered: true });
  } else {
    blocks.push({ type: 'para', text, centered: false });
  }
}

// ---------- 3. merge ----------
// a) consecutive verse blocks → one verse
// b) paragraph fragments broken mid-sentence (no terminal punctuation) → joined with the next paragraph,
//    unless the next one is a new dialogue turn
const TERMINAL = /[.!?:…“”‘’"»)]$/;
const final = [];
for (const b of blocks) {
  const prev = final[final.length - 1];
  if (b.type === 'verse' && prev && prev.type === 'verse') { prev.lines.push(...b.lines); continue; }
  if (b.type === 'para' && !b.speaker && prev && prev.type === 'para' && prev.text && !TERMINAL.test(prev.text)) {
    prev.text += ' ' + b.text; continue;
  }
  final.push({ ...b });
}

// translations = centered paragraphs directly following a verse (or its source line)
final.forEach((b, i) => {
  const p = final[i - 1];
  if (b.type === 'para' && !b.speaker && p && (p.type === 'verse' || p.type === 'source')) {
    b.translation = b.centered = true;
  }
});

// ---------- 4. DOCX ----------
const pt = n => n * 2; // docx half-points
const children = [];
for (const b of final) {
  if (b.type === 'title') {
    children.push(new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { after: 480 },
      children: [new TextRun({ text: b.text, bold: true, size: pt(18), font: BODY_FONT })],
    }));
  } else if (b.type === 'verse') {
    b.lines.forEach((line, i) => children.push(new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: i === 0 ? 240 : 0, after: i === b.lines.length - 1 ? 200 : 0, line: 300 },
      keepNext: true, keepLines: true,
      children: [new TextRun({ text: line, italics: true, size: pt(11.5), font: SKT_FONT, color: '000000' })],
    })));
  } else if (b.type === 'source') {
    children.push(new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { before: 0, after: 200 }, keepNext: true,
      children: [new TextRun({ text: b.text, size: pt(9.5), font: BODY_FONT, color: '555555' })],
    }));
  } else {
    const runs = [];
    if (b.speaker) runs.push(new TextRun({ text: b.speaker + ': ', bold: true, size: pt(12), font: BODY_FONT }));
    if (b.text) runs.push(new TextRun({ text: b.text, size: pt(12), font: BODY_FONT }));
    children.push(new Paragraph({
      alignment: b.centered ? AlignmentType.CENTER : AlignmentType.JUSTIFIED,
      indent: b.centered ? { left: 567, right: 567 } : undefined,
      spacing: { after: b.translation ? 280 : 160, line: 312 }, keepNext: !b.text,
      children: runs,
    }));
  }
}

const doc = new Document({
  creator: 'Jaiva Dharma – český překlad',
  title: final[0].type === 'title' ? final[0].text : 'Jaiva Dharma',
  styles: { default: { document: { run: { font: BODY_FONT, size: pt(12) } } } },
  sections: [{
    properties: { page: { margin: { top: 1418, bottom: 1418, left: 1418, right: 1418 } } }, // 2.5 cm, A4 default
    children,
  }],
});

// ---------- 5. HTML (for PDF) ----------
const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const html = [];
for (const b of final) {
  if (b.type === 'title') html.push(`<h1>${esc(b.text)}</h1>`);
  else if (b.type === 'verse') html.push(`<div class="verse">${b.lines.map(l => `<div>${esc(l)}</div>`).join('')}</div>`);
  else if (b.type === 'source') html.push(`<div class="source">${esc(b.text)}</div>`);
  else {
    const cls = [b.centered && 'center', b.translation && 'translation'].filter(Boolean).join(' ');
    html.push(`<p${cls ? ` class="${cls}"` : ''}>${b.speaker ? `<b>${esc(b.speaker)}:</b> ` : ''}${esc(b.text)}</p>`);
  }
}
const page = `<!doctype html><html lang="cs"><head><meta charset="utf-8"><title>${esc(final[0].text)}</title>
<style>
@page { size: A4; margin: 25mm; @bottom-center { content: counter(page); font-size: 9pt; } }
body { font-family: "${BODY_FONT}", serif; font-size: 12pt; line-height: 1.45; color: #000; hyphens: auto; }
h1 { text-align: center; font-size: 18pt; margin: 0 0 28pt; }
p { text-align: justify; margin: 0 0 8pt; }
p.center { text-align: center; margin-left: 1cm; margin-right: 1cm; }
p.translation { margin-bottom: 14pt; }
.verse { text-align: center; font-family: "${SKT_FONT}", serif; font-style: italic;
         font-size: 11.5pt; line-height: 1.5; color: #000; margin: 12pt 0 10pt; break-inside: avoid; break-after: avoid; }
.source { text-align: center; font-size: 9.5pt; color: #555; margin: -4pt 0 10pt; break-after: avoid; }
</style></head><body>
${html.join('\n')}
</body></html>`;

fs.writeFileSync(htmlPath, page);
Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(docxPath, buf);
  execFileSync(CHROME, ['--headless', '--disable-gpu', '--no-pdf-header-footer',
    '--print-to-pdf=' + pdfPath, 'file://' + htmlPath], { stdio: 'ignore' });
  fs.unlinkSync(htmlPath);
  console.log('DOCX:', path.relative(ROOT, docxPath));
  console.log('PDF: ', path.relative(ROOT, pdfPath));
});
