export type DescriptionBlock =
  | { readonly kind: 'heading'; readonly text: string }
  | { readonly kind: 'paragraph'; readonly text: string }
  | { readonly kind: 'list'; readonly items: readonly string[] };

const headingMarker = /^#{1,6}\s*$/u;
const markdownHeading = /^#{1,6}\s+(.+)$/u;
const boldHeading = /^\*\*([^*]+)\*\*:?$/u;
const listItem = /^(?:[-*•▪◦]|\d{1,2}[.)])\s+(.+)$/u;

export function descriptionBlocks(text: string): DescriptionBlock[] {
  const blocks: DescriptionBlock[] = [];
  let paragraph: string[] = [];
  let items: string[] = [];
  let headingNext = false;
  const flush = (): void => {
    if (paragraph.length) {
      blocks.push({ kind: 'paragraph', text: paragraph.join('\n') });
    }
    if (items.length) {
      blocks.push({ kind: 'list', items });
    }
    paragraph = [];
    items = [];
  };
  for (const raw of text.split(/\r?\n/u)) {
    const line = raw.trim();
    if (!line) {
      flush();
      continue;
    }
    if (headingMarker.test(line)) {
      flush();
      headingNext = true;
      continue;
    }
    const heading = headingNext
      ? line
      : (markdownHeading.exec(line)?.[1] ?? boldHeading.exec(line)?.[1]);
    headingNext = false;
    if (heading !== undefined) {
      flush();
      blocks.push({ kind: 'heading', text: plain(heading).replace(/:$/u, '') });
      continue;
    }
    const item = listItem.exec(line)?.[1];
    if (item !== undefined) {
      if (paragraph.length) {
        flush();
      }
      items.push(plain(item));
      continue;
    }
    if (items.length) {
      flush();
    }
    paragraph.push(plain(line));
  }
  flush();
  return blocks;
}

function plain(text: string): string {
  return text.replace(/\*\*(.+?)\*\*/gu, '$1').trim();
}
