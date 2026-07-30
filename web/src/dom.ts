/** Minimal element builder.
 *
 * Curated summaries and topic names come from JSON that contributors edit, so they are treated as
 * text rather than markup throughout — textContent everywhere, no innerHTML.
 */
export function el(
  tag: string,
  attrs: Record<string, string> = {},
  children: (Node | string)[] = [],
): HTMLElement {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    node.setAttribute(key, value);
  }
  for (const child of children) {
    node.append(typeof child === 'string' ? document.createTextNode(child) : child);
  }
  return node;
}

export function formatNumber(value: number): string {
  return value.toLocaleString('en-US');
}

/** Chip marking where a claim comes from. The distinction between measured and written is the
 * one thing this interface must never blur, so it is a shared component rather than a per-view
 * styling choice. */
export function provenanceChip(
  kind: 'measured' | 'curated' | 'generated' | 'unvalidated',
): HTMLElement {
  const labels = {
    measured: 'measured',
    curated: 'written by a person',
    generated: 'generated from contracts',
    unvalidated: 'failed validation',
  };
  return el('span', { class: `chip chip-${kind}` }, [labels[kind]]);
}
