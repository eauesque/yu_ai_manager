/**
 * shared/dialog.ts — typed wrappers over the global window.customConfirm
 * / customAlert / customPrompt helpers defined in
 * ui/default/static/dialog.js (loaded via _nav.html).
 *
 * Always use these instead of window.confirm / alert / prompt, which are
 * inconsistent in Tauri and ignore dark-mode CSS variables.
 * See docs/development/development_docs/UI_DIALOG_POLICY.md.
 */

export interface ConfirmOptions {
  okText?: string;
  cancelText?: string;
  /** When true, primary button uses the danger (red) color. */
  danger?: boolean;
}

export interface AlertOptions {
  okText?: string;
}

export interface PromptOptions {
  okText?: string;
  cancelText?: string;
  placeholder?: string;
  /** When true, render a textarea instead of a single-line input. */
  multiline?: boolean;
}

type Win = typeof window & {
  customConfirm?: (m: string, o?: ConfirmOptions) => Promise<boolean>;
  customAlert?: (m: string, o?: AlertOptions) => Promise<void>;
  customPrompt?: (m: string, d?: string | null, o?: PromptOptions) => Promise<string | null>;
};

function w(): Win {
  return window as Win;
}

export function customConfirm(message: string, options?: ConfirmOptions): Promise<boolean> {
  const fn = w().customConfirm;
  if (typeof fn !== 'function') {
    // Hard fail in dev so missing dialog.js is obvious; in prod, fall back to native.
    console.error('[shared/dialog] window.customConfirm missing — is /static/dialog.js loaded?');
    return Promise.resolve(window.confirm(message));
  }
  return fn(message, options);
}

export function customAlert(message: string, options?: AlertOptions): Promise<void> {
  const fn = w().customAlert;
  if (typeof fn !== 'function') {
    console.error('[shared/dialog] window.customAlert missing — is /static/dialog.js loaded?');
    window.alert(message);
    return Promise.resolve();
  }
  return fn(message, options);
}

export function customPrompt(
  message: string,
  defaultValue?: string | null,
  options?: PromptOptions,
): Promise<string | null> {
  const fn = w().customPrompt;
  if (typeof fn !== 'function') {
    console.error('[shared/dialog] window.customPrompt missing — is /static/dialog.js loaded?');
    return Promise.resolve(window.prompt(message, defaultValue ?? '') ?? null);
  }
  return fn(message, defaultValue, options);
}
