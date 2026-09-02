/**
 * Search modal and quick focus helpers.
 */

import { activate as focusTrapActivate, deactivate as focusTrapDeactivate } from '../../a11y/focus-trap';
import { getRuntimeInitApi, getSearchResultsApi } from '../../shared/browser-apis';

declare global {
  interface Window {
    openSearchOrModal?: () => void;
    openSearchModal?: () => void;
    closeSearchModal?: () => void;
    executeSearchModal?: () => void;
    isSearchBarVisible?: () => boolean;
  }
}

export function isSearchBarVisible(): boolean {
  const searchBar = document.getElementById('tagQuery');
  if (!searchBar) return false;
  const rect = searchBar.getBoundingClientRect();
  return rect.bottom > 0 && rect.top < window.innerHeight;
}

export function openSearchOrModal(): void {
  const savedPos = window.scrollY;
  if (savedPos > 200) window.showScrollBackBtn?.(savedPos);
  if (isSearchBarVisible()) {
    const q = document.getElementById('tagQuery') as HTMLInputElement | null;
    if (q) {
      q.focus();
      q.select();
    }
    return;
  }
  window.scrollTo({ top: 0, behavior: 'smooth' });
  setTimeout(() => {
    const q = document.getElementById('tagQuery') as HTMLInputElement | null;
    if (q) {
      q.focus();
      q.select();
    }
  }, 400);
}

export function openSearchModal(): void {
  const modal = document.getElementById('searchModal');
  if (!modal) return;
  const input = document.getElementById('searchModalInput') as HTMLInputElement | null;
  const mainInput = document.getElementById('tagQuery') as HTMLInputElement | null;
  if (input && mainInput) input.value = mainInput.value;
  (
    [
      ['modelFilter', 'smModelFilter'],
      ['sortBy', 'smSortBy'],
      ['inPrompt', 'smInPrompt'],
      ['inPath', 'smInPath'],
    ] as [string, string][]
  ).forEach(function (p) {
    const m = document.getElementById(p[0]) as HTMLInputElement | HTMLSelectElement | null;
    const s = document.getElementById(p[1]) as HTMLInputElement | HTMLSelectElement | null;
    if (m && s) s.value = m.value;
  });
  // Sync checkbox state
  (
    [
      ['hasTags', 'smHasTags'],
      ['aiAnalyzed', 'smAiAnalyzed'],
    ] as [string, string][]
  ).forEach(function (p) {
    const m = document.getElementById(p[0]) as HTMLInputElement | null;
    const s = document.getElementById(p[1]) as HTMLInputElement | null;
    if (m && s) s.checked = m.checked;
  });
  modal.style.display = 'flex';
  focusTrapActivate(modal, closeSearchModal);
  if (input) {
    input.focus();
    input.select();
    input.onkeydown = function (e: KeyboardEvent): void {
      if (e.key === 'Enter') {
        e.preventDefault();
        executeSearchModal();
      }
    };
  }
}

export function closeSearchModal(): void {
  const modal = document.getElementById('searchModal');
  if (modal) {
    modal.style.display = 'none';
    focusTrapDeactivate(modal);
  }
}

export function executeSearchModal(): void {
  const runtimeInitApi = getRuntimeInitApi();
  const searchResultsApi = getSearchResultsApi();
  const input = document.getElementById('searchModalInput') as HTMLInputElement | null;
  const mainInput = document.getElementById('tagQuery') as HTMLInputElement | null;
  if (input && mainInput) {
    mainInput.value = input.value;
    runtimeInitApi.saveSearchState();
  }
  (
    [
      ['modelFilter', 'smModelFilter'],
      ['sortBy', 'smSortBy'],
      ['inPrompt', 'smInPrompt'],
      ['inPath', 'smInPath'],
    ] as [string, string][]
  ).forEach(function (p) {
    const m = document.getElementById(p[0]) as HTMLInputElement | HTMLSelectElement | null;
    const s = document.getElementById(p[1]) as HTMLInputElement | HTMLSelectElement | null;
    if (m && s) m.value = s.value;
  });
  // Sync checkbox state back to main form
  (
    [
      ['hasTags', 'smHasTags'],
      ['aiAnalyzed', 'smAiAnalyzed'],
    ] as [string, string][]
  ).forEach(function (p) {
    const m = document.getElementById(p[0]) as HTMLInputElement | null;
    const s = document.getElementById(p[1]) as HTMLInputElement | null;
    if (m && s) m.checked = s.checked;
  });
  closeSearchModal();
  searchResultsApi.runSearch();
}
