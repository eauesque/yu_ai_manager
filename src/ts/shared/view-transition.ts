/**
 * Safe wrapper for document.startViewTransition.
 *
 * Firefox (as of 2026-03) exposes `document.startViewTransition` but throws
 * DOMException in several situations (document hidden, unsupported options).
 * This wrapper catches those errors and falls back to direct execution.
 */

export function suppressViewTransitionRejections(transition: ViewTransition): ViewTransition {
  transition.ready.catch(() => { /* ignored */ });
  transition.updateCallbackDone.catch(() => { /* ignored */ });
  transition.finished.catch(() => { /* ignored */ });
  return transition;
}

export function safeViewTransition(fn: () => void): void {
  if (!document.startViewTransition || document.hidden) {
    fn();
    return;
  }
  try {
    suppressViewTransitionRejections(document.startViewTransition(fn));
  } catch {
    fn();
  }
}
