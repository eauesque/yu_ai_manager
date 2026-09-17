/**
 * MD Viewer vendor bundle: marked + highlight.js (major languages only)
 *
 * Exposed globally for use from extension template inline scripts.
 */

import { marked } from 'marked';
import hljs from 'highlight.js/lib/core';

// Register only 8 major languages (to reduce bundle size)
import python from 'highlight.js/lib/languages/python';
import javascript from 'highlight.js/lib/languages/javascript';
import typescript from 'highlight.js/lib/languages/typescript';
import json from 'highlight.js/lib/languages/json';
import bash from 'highlight.js/lib/languages/bash';
import sql from 'highlight.js/lib/languages/sql';
import css from 'highlight.js/lib/languages/css';
import xml from 'highlight.js/lib/languages/xml';

hljs.registerLanguage('python', python);
hljs.registerLanguage('javascript', javascript);
hljs.registerLanguage('typescript', typescript);
hljs.registerLanguage('json', json);
hljs.registerLanguage('bash', bash);
hljs.registerLanguage('sql', sql);
hljs.registerLanguage('css', css);
hljs.registerLanguage('xml', xml);

// Integrate highlight.js into marked
marked.setOptions({
  highlight(code: string, lang: string): string {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value;
    }
    return hljs.highlightAuto(code).value;
  },
} as any);

// Expose globally
(window as any)._mdvMarked = marked;
(window as any)._mdvHljs = hljs;
