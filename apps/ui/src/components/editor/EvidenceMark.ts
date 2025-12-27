import { Mark, mergeAttributes } from '@tiptap/core';

export const EvidenceMark = Mark.create({
  name: 'evidenceRef',
  inclusive: false,

  addAttributes() {
    return {
      refs: {
        default: [],
        parseHTML: (element) => {
          const raw = element.getAttribute('data-evidence-refs');
          if (!raw) return [];
          try {
            const parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed : [];
          } catch {
            return [];
          }
        },
        renderHTML: (attrs) => {
          const refs = Array.isArray(attrs.refs) ? attrs.refs : [];
          return {
            'data-evidence-refs': JSON.stringify(refs),
            title: refs.length ? `Evidence: ${refs.join(', ')}` : undefined,
          };
        },
      },
    };
  },

  parseHTML() {
    return [{ tag: 'span[data-evidence-refs]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return ['span', mergeAttributes(HTMLAttributes, { class: 'evidence-mark' }), 0];
  },
});
