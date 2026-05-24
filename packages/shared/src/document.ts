import type { DocType } from './enums';

export type BlockType =
  | 'heading'
  | 'paragraph'
  | 'list_item'
  | 'table'
  | 'caption'
  | 'figure'
  | 'footnote'
  | 'header'
  | 'footer'
  | 'page_number'
  | 'equation';

export interface TableCell {
  text: string;
  translatedText?: string;
}

export interface DocBlock {
  id: string;
  type: BlockType;
  level?: number; // heading level (1-6) or list depth
  text: string; // empty for tables (cells hold the text)
  translatedText?: string;
  cells?: TableCell[][]; // table rows × cols
  bbox?: [number, number, number, number]; // PDF points; absent for DOCX/TXT
  font?: { family?: string; size?: number; bold?: boolean };
  assetId?: string; // links to a DocumentAsset (image/table)
  referenceLabel?: string; // e.g. "Figure 4"
  page: number;
  order: number; // global reading order
}

export interface DocPage {
  number: number;
  width?: number;
  height?: number;
  blocks: DocBlock[];
}

export interface OutlineEntry {
  title: string;
  level: number;
  blockId: string;
}

export interface DocumentTree {
  docType: DocType;
  pages: DocPage[];
  outline: OutlineEntry[];
}

/** One translatable chunk produced by the chunker (maps to a DB TranslationChunk row). */
export interface ChunkInput {
  chapterIndex: number;
  sectionTitle?: string;
  chunkIndex: number;
  blockIds: string[];
  sourceText: string;
  prevContext?: string;
}

/** Flatten a document tree into reading order. */
export function flattenBlocks(tree: DocumentTree): DocBlock[] {
  return tree.pages
    .flatMap((p) => p.blocks)
    .sort((a, b) => a.order - b.order);
}
