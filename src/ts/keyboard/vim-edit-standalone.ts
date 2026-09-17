/**
 * Standalone entry point for vim-edit keyboard helpers.
 * Used by extension pages that need vim-style editing without the full keyboard bundle.
 */
import { handleVimNavigation, handleCtrlShortcuts } from './vim-edit';

(window as any).keyboardPowerVimEdit = { handleVimNavigation, handleCtrlShortcuts };
