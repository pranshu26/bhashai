import { describe, it, expect } from 'vitest';
import type { DocumentTree, DocBlock } from '@bhashai/shared';
import { chunkDocument, splitSentences } from './chunker';

let n = 0;
function b(partial: Partial<DocBlock> & { type: DocBlock['type']; text: string }): DocBlock {
  return { id: `b${n}`, page: 1, order: n++, ...partial };
}
function tree(blocks: DocBlock[]): DocumentTree {
  return { docType: 'TXT', pages: [{ number: 1, blocks }], outline: [] };
}

describe('chunkDocument', () => {
  it('keeps reading order and attaches a heading to the section it introduces', () => {
    n = 0;
    const t = tree([
      b({ type: 'heading', level: 1, text: 'Chapter 1 Introduction' }),
      b({ type: 'paragraph', text: 'First paragraph of the intro.' }),
      b({ type: 'paragraph', text: 'Second paragraph of the intro.' }),
    ]);
    const chunks = chunkDocument(t, { maxChars: 5000 });
    expect(chunks).toHaveLength(1);
    expect(chunks[0].sectionTitle).toBe('Chapter 1 Introduction');
    expect(chunks[0].chapterIndex).toBe(1);
    expect(chunks[0].sourceText).toContain('Chapter 1 Introduction');
    expect(chunks[0].sourceText).toContain('First paragraph');
    expect(chunks[0].chunkIndex).toBe(0);
  });

  it('increments chapterIndex per level-1 heading and tracks section titles', () => {
    n = 0;
    const t = tree([
      b({ type: 'heading', level: 1, text: 'Chapter 1' }),
      b({ type: 'paragraph', text: 'Intro text.' }),
      b({ type: 'heading', level: 2, text: '1.1 Background' }),
      b({ type: 'paragraph', text: 'Background text.' }),
      b({ type: 'heading', level: 1, text: 'Chapter 2' }),
      b({ type: 'paragraph', text: 'Second chapter text.' }),
    ]);
    const chunks = chunkDocument(t, { maxChars: 5000 });
    const ch2 = chunks.find((c) => c.sourceText.includes('Second chapter text'))!;
    const bg = chunks.find((c) => c.sourceText.includes('Background text'))!;
    expect(bg.sectionTitle).toBe('1.1 Background');
    expect(bg.chapterIndex).toBe(1);
    expect(ch2.chapterIndex).toBe(2);
    // global order preserved
    expect(chunks.map((c) => c.chunkIndex)).toEqual([...chunks.keys()]);
  });

  it('keeps a table whole in its own chunk', () => {
    n = 0;
    const t = tree([
      b({ type: 'paragraph', text: 'Before table.' }),
      b({ type: 'table', text: '', cells: [[{ text: 'A' }, { text: 'B' }], [{ text: '1' }, { text: '2' }]] }),
      b({ type: 'paragraph', text: 'After table.' }),
    ]);
    const chunks = chunkDocument(t, { maxChars: 5000 });
    const tableChunk = chunks.find((c) => c.sourceText.includes('A\tB'))!;
    expect(tableChunk).toBeTruthy();
    expect(tableChunk.sourceText).toBe('A\tB\n1\t2');
  });

  it('splits an oversized paragraph only at sentence boundaries', () => {
    n = 0;
    const sentence = 'This is a sentence of moderate length. ';
    const big = sentence.repeat(20).trim(); // ~780 chars, 20 sentences
    const t = tree([b({ type: 'paragraph', text: big })]);
    const chunks = chunkDocument(t, { maxChars: 120 });
    expect(chunks.length).toBeGreaterThan(1);
    for (const c of chunks) {
      expect(c.sourceText.trim()).toMatch(/[.?!।]$/); // every piece ends on a sentence boundary
    }
    // no sentence content lost
    const rejoined = chunks.map((c) => c.sourceText).join(' ');
    expect((rejoined.match(/sentence of moderate length/g) ?? []).length).toBe(20);
  });

  it('carries previous-chunk context forward', () => {
    n = 0;
    const t = tree([
      b({ type: 'heading', level: 1, text: 'A' }),
      b({ type: 'paragraph', text: 'x'.repeat(1900) }),
      b({ type: 'heading', level: 1, text: 'B' }),
      b({ type: 'paragraph', text: 'second' }),
    ]);
    const chunks = chunkDocument(t, { maxChars: 1800 });
    expect(chunks[0].prevContext).toBeUndefined();
    expect(chunks[1].prevContext).toBeTruthy();
  });
});

describe('splitSentences', () => {
  it('never breaks a sentence', () => {
    const text = 'One sentence here. Another sentence follows! A third? Yes.';
    const pieces = splitSentences(text, 25);
    for (const p of pieces) expect(p).toMatch(/[.?!]$/);
    expect(pieces.join(' ').replace(/\s+/g, ' ')).toContain('Another sentence follows!');
  });

  it('handles the Devanagari danda terminator', () => {
    const text = 'पहला वाक्य। दूसरा वाक्य। तीसरा वाक्य।';
    const pieces = splitSentences(text, 12);
    expect(pieces.length).toBeGreaterThan(1);
    for (const p of pieces) expect(p.trim()).toMatch(/।$/);
  });
});
