import { el, formatNumber } from '../dom';
import type { Taxonomy, TaxonomyNode } from '../types';

/** The tree is scaffolding, so it renders as scaffolding: collapsed, quiet, navigable.
 *
 * Topics are listed under each subfield but capped, because a subfield holding 54 topics turns
 * the page into a directory listing and buries the holes, which are the point. */
const TOPICS_PER_SUBFIELD = 8;

function groupBy(nodes: TaxonomyNode[], key: 'domain' | 'field' | 'subfield') {
  const groups = new Map<string, TaxonomyNode[]>();
  for (const node of nodes) {
    const parent = node[key];
    if (!parent) continue;
    const bucket = groups.get(parent);
    if (bucket) bucket.push(node);
    else groups.set(parent, [node]);
  }
  return groups;
}

function subfieldBlock(subfield: TaxonomyNode, topics: TaxonomyNode[]): HTMLElement {
  const sorted = [...topics].sort((a, b) => b.works_count - a.works_count);
  const shown = sorted.slice(0, TOPICS_PER_SUBFIELD);
  const hidden = sorted.length - shown.length;

  const items = shown.map((topic) =>
    el('li', {}, [
      el('span', { class: 'topic-name' }, [topic.display_name]),
      el('span', { class: 'topic-count num' }, [formatNumber(topic.works_count)]),
    ]),
  );
  if (hidden > 0) {
    items.push(el('li', { class: 'more' }, [`+${hidden} more topics`]));
  }

  return el('details', { class: 'subfield' }, [
    el('summary', {}, [
      subfield.display_name,
      el('span', { class: 'topic-count num' }, [`${sorted.length} topics`]),
    ]),
    el('ul', { class: 'topics' }, items),
  ]);
}

export function renderTaxonomy(taxonomy: Taxonomy): HTMLElement {
  const fieldsByDomain = groupBy(taxonomy.fields, 'domain');
  const subfieldsByField = groupBy(taxonomy.subfields, 'field');
  const topicsBySubfield = groupBy(taxonomy.topics, 'subfield');

  const domains = taxonomy.domains.map((domain) =>
    el('details', { class: 'domain' }, [
      el('summary', {}, [domain.display_name]),
      ...(fieldsByDomain.get(domain.id) ?? []).map((field) =>
        el('details', { class: 'field' }, [
          el('summary', {}, [field.display_name]),
          ...(subfieldsByField.get(field.id) ?? []).map((subfield) =>
            subfieldBlock(subfield, topicsBySubfield.get(subfield.id) ?? []),
          ),
        ]),
      ),
    ]),
  );

  return el('section', { class: 'layer' }, [
    el('h2', {}, ['The tree']),
    el('p', { class: 'blurb' }, [
      'OpenAlex classifies published work into four domains, 26 fields, 252 subfields and 4,516 ' +
        'topics. It is scaffolding for the holes, not the subject — and it only covers what got ' +
        'published in an indexed venue.',
    ]),
    el('div', { class: 'tree' }, domains),
  ]);
}
