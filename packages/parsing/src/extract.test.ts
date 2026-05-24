import { describe, it, expect } from 'vitest';
import { extractTxt, detectDocType } from './extract';
import { chunkDocument } from './chunker';

describe('detectDocType', () => {
  it('maps extensions and mime types', () => {
    expect(detectDocType('a.txt')).toBe('TXT');
    expect(detectDocType('thesis.docx')).toBe('DOCX');
    expect(detectDocType('report.pdf')).toBe('PDF_TEXT');
    expect(detectDocType('x', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')).toBe('DOCX');
  });
});

describe('extractTxt', () => {
  const sample = [
    'CHAPTER ONE',
    '',
    'This is the first paragraph. It has two sentences.',
    '',
    '1. Introduction',
    '',
    'Body text under the numbered heading.',
    '',
    '- first item',
    '- second item',
  ].join('\n');

  it('detects headings, lists, and paragraphs with order preserved', () => {
    const tree = extractTxt(Buffer.from(sample));
    const blocks = tree.pages[0].blocks;
    expect(blocks[0]).toMatchObject({ type: 'heading', level: 1, text: 'CHAPTER ONE' });
    expect(blocks[1]).toMatchObject({ type: 'paragraph' });
    expect(blocks[2]).toMatchObject({ type: 'heading', text: '1. Introduction' });
    expect(blocks.filter((b) => b.type === 'list_item')).toHaveLength(2);
    expect(blocks.at(-1)).toMatchObject({ type: 'list_item', text: 'second item' });
    expect(tree.outline.length).toBeGreaterThanOrEqual(2);
  });

  it('feeds cleanly into the chunker', () => {
    const tree = extractTxt(Buffer.from(sample));
    const chunks = chunkDocument(tree, { maxChars: 5000 });
    expect(chunks.length).toBeGreaterThan(0);
    expect(chunks[0].sectionTitle).toBe('CHAPTER ONE');
    expect(chunks.map((c) => c.chunkIndex)).toEqual([...chunks.keys()]);
  });
});
