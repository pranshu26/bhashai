import * as mammoth from 'mammoth';
import { parse as parseHtml, HTMLElement } from 'node-html-parser';
import type { DocumentTree, DocBlock, DocType, OutlineEntry } from '@bhashai/shared';

export interface ExtractInput {
  buffer: Buffer;
  filename: string;
  mime?: string;
}

export function detectDocType(filename: string, mime?: string): DocType {
  const ext = filename.toLowerCase().split('.').pop() ?? '';
  if (ext === 'txt' || mime === 'text/plain') return 'TXT';
  if (ext === 'docx' || (mime ?? '').includes('word')) return 'DOCX';
  if (ext === 'pdf' || mime === 'application/pdf') return 'PDF_TEXT';
  return 'TXT';
}

export async function extractDocument(input: ExtractInput): Promise<DocumentTree> {
  const docType = detectDocType(input.filename, input.mime);
  if (docType === 'TXT') return extractTxt(input.buffer);
  if (docType === 'DOCX') return extractDocx(input.buffer);
  throw new Error(
    'PDF parsing is handled by the parser-service (Phase 2) and is not available in Phase 1 Node parsing.',
  );
}

// ---------- TXT ----------
function headingLevel(line: string): number | null {
  if (line.length > 90) return null;
  if (/^(chapter|part)\b/i.test(line)) return 1;
  if (/^(section)\b/i.test(line)) return 2;
  const numbered = line.match(/^(\d+)(\.\d+)*\.?\s+\S/);
  if (numbered) return Math.min(6, (line.match(/\./g)?.length ?? 0) + 1);
  if (line.length < 60 && /[A-Za-z]/.test(line) && line === line.toUpperCase() && !/[.?!]$/.test(line))
    return 1;
  return null;
}

export function extractTxt(buffer: Buffer): DocumentTree {
  const raw = buffer.toString('utf8').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  const groups = raw.split(/\n{2,}/);
  const blocks: DocBlock[] = [];
  const outline: OutlineEntry[] = [];
  let order = 0;

  for (const group of groups) {
    const lines = group.split('\n').map((l) => l.trim()).filter(Boolean);
    if (lines.length === 0) continue;

    if (lines.length === 1) {
      const lvl = headingLevel(lines[0]);
      if (lvl !== null) {
        const id = `b${order}`;
        blocks.push({ id, type: 'heading', level: lvl, text: lines[0], page: 1, order: order++ });
        outline.push({ title: lines[0], level: lvl, blockId: id });
        continue;
      }
    }

    const isList = lines.every((l) => /^([-*•]|\d+[.)])\s+/.test(l));
    if (isList) {
      for (const l of lines) {
        blocks.push({
          id: `b${order}`,
          type: 'list_item',
          text: l.replace(/^([-*•]|\d+[.)])\s+/, ''),
          page: 1,
          order: order++,
        });
      }
      continue;
    }

    blocks.push({ id: `b${order}`, type: 'paragraph', text: lines.join(' '), page: 1, order: order++ });
  }

  return { docType: 'TXT', pages: [{ number: 1, blocks }], outline };
}

// ---------- DOCX (Node, via mammoth) ----------
export async function extractDocx(buffer: Buffer): Promise<DocumentTree> {
  const { value: html } = await mammoth.convertToHtml({ buffer });
  const root = parseHtml(html);
  const blocks: DocBlock[] = [];
  const outline: OutlineEntry[] = [];
  let order = 0;

  for (const node of root.childNodes) {
    if (!(node instanceof HTMLElement)) continue;
    const tag = (node.tagName ?? '').toLowerCase();

    if (/^h[1-6]$/.test(tag)) {
      const level = Number(tag[1]);
      const text = node.text.trim();
      if (!text) continue;
      const id = `b${order}`;
      blocks.push({ id, type: 'heading', level, text, page: 1, order: order++ });
      outline.push({ title: text, level, blockId: id });
    } else if (tag === 'p') {
      const text = node.text.trim();
      if (text) blocks.push({ id: `b${order}`, type: 'paragraph', text, page: 1, order: order++ });
    } else if (tag === 'ul' || tag === 'ol') {
      for (const li of node.querySelectorAll('li')) {
        const text = li.text.trim();
        if (text) blocks.push({ id: `b${order}`, type: 'list_item', text, page: 1, order: order++ });
      }
    } else if (tag === 'table') {
      const cells = node
        .querySelectorAll('tr')
        .map((tr) => tr.querySelectorAll('th,td').map((td) => ({ text: td.text.trim() })));
      if (cells.length) blocks.push({ id: `b${order}`, type: 'table', text: '', cells, page: 1, order: order++ });
    } else if (tag === 'img') {
      blocks.push({ id: `b${order}`, type: 'figure', text: '', page: 1, order: order++ });
    } else {
      const text = node.text.trim();
      if (text) blocks.push({ id: `b${order}`, type: 'paragraph', text, page: 1, order: order++ });
    }
  }

  return { docType: 'DOCX', pages: [{ number: 1, blocks }], outline };
}
