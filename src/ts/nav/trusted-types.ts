/**
 * Trusted Types policy setup.
 *
 * Creates a 'default' policy that sanitizes all innerHTML/outerHTML
 * assignments via DOMPurify. This prevents XSS even if raw strings
 * are accidentally passed to sink APIs.
 *
 * Must be imported early (before any DOM manipulation).
 */

import DOMPurify from 'dompurify';

interface TrustedTypesApi {
  defaultPolicy?: unknown;
  createPolicy: (
    name: string,
    rules: {
      createHTML?: (input: string) => string;
      createScriptURL?: (input: string) => string;
      createScript?: (input: string) => string;
    },
  ) => unknown;
}

declare global {
  interface Window {
    trustedTypes?: TrustedTypesApi;
  }
}

/** Initialize Trusted Types if the browser supports it. */
export function initTrustedTypes(): void {
  const tt = window.trustedTypes;
  if (typeof tt === 'undefined') return;

  // 'dompurify' policy: used by DOMPurify internally
  if (!tt.defaultPolicy) {
    try {
      tt.createPolicy('default', {
        createHTML: (input: string) => DOMPurify.sanitize(input, { RETURN_TRUSTED_TYPE: false }) as string,
        createScriptURL: (input: string) => input,
        createScript: (input: string) => input,
      });
    } catch {
      // Policy already exists or Trusted Types not fully supported
    }
  }
}
