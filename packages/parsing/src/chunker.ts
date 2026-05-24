import { type DocumentTree, type DocBlock, type ChunkInput, flattenBlocks } from '@bhashai/shared';

export interface ChunkOptions {
  /** Soft upper bound on a chunk's character count. */
  maxChars?: number;
  /** Characters of the previous chunk carried forward as context. */
  contextChars?: number;
}

const DEFAULT_MAX = 1800;
const DEFAULT_CONTEXT = 240;

/**
 * Split a document tree into ordered, structure-aware chunks:
 * - never splits a paragraph mid-sentence (oversized paragraphs split on sentence ends),
 * - a heading begins a new section and stays attached to the chunk it introduces,
 * - tables are kept whole in their own chunk,
 * - chunkIndex preserves global order; each chunk carries a tail of the previous as context.
 */
export function chunkDocument(tree: DocumentTree, opts: ChunkOptions = {}): ChunkInput[] {
  const maxChars = opts.maxChars ?? DEFAULT_MAX;
  const contextChars = opts.contextChars ?? DEFAULT_CONTEXT;
  const blocks = flattenBlocks(tree);
  const chunks: ChunkInput[] = [];

  let chapterIndex = 0;
  let sectionTitle: string | undefined;
  let chunkIndex = 0;

  let bufIds: string[] = [];
  let bufParts: string[] = [];
  let bufLen = 0;

  const push = (blockIds: string[], sourceText: string) => {
    const text = sourceText.trim();
    if (!text) return;
    const prev = chunks[chunks.length - 1];
    chunks.push({
      chapterIndex,
      sectionTitle,
      chunkIndex: chunkIndex++,
      blockIds,
      sourceText: text,
      prevContext: prev ? tail(prev.sourceText, contextChars) : undefined,
    });
  };

  const flush = () => {
    if (bufIds.length) push([...bufIds], bufParts.join('\n\n'));
    bufIds = [];
    bufParts = [];
    bufLen = 0;
  };

  for (const b of blocks) {
    if (b.type === 'heading') {
      flush();
      if ((b.level ?? 1) <= 1) chapterIndex++;
      sectionTitle = b.text.trim() || sectionTitle;
      bufIds.push(b.id);
      bufParts.push(b.text.trim());
      bufLen += b.text.length;
      continue;
    }

    if (b.type === 'table') {
      flush();
      push([b.id], tableToText(b));
      continue;
    }

    const text = b.text.trim();
    if (!text) continue;

    if (text.length > maxChars) {
      flush();
      for (const piece of splitSentences(text, maxChars)) push([b.id], piece);
      continue;
    }

    if (bufLen + text.length > maxChars && bufIds.length) flush();
    bufIds.push(b.id);
    bufParts.push(text);
    bufLen += text.length;
  }
  flush();
  return chunks;
}

/** Greedily pack whole sentences into pieces ≤ maxChars; a lone over-long sentence is kept intact. */
export function splitSentences(text: string, maxChars: number): string[] {
  const sentences = text.match(/[^.?!।]+[.?!।]+[\s]*|[^.?!।]+$/g) ?? [text];
  const pieces: string[] = [];
  let cur = '';
  for (const s of sentences) {
    if (cur && cur.length + s.length > maxChars) {
      pieces.push(cur.trim());
      cur = '';
    }
    cur += s;
  }
  if (cur.trim()) pieces.push(cur.trim());
  return pieces;
}

function tableToText(b: DocBlock): string {
  if (!b.cells) return b.text;
  return b.cells.map((row) => row.map((c) => c.text).join('\t')).join('\n');
}

function tail(text: string, n: number): string {
  if (text.length <= n) return text;
  return '…' + text.slice(text.length - n);
}
