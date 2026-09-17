/**
 * pick-folder.ts -- typed access to the shared folder picker.
 *
 * The implementation lives in ui/default/static/dir-picker-fallback.js
 * (a classic script, so it is reachable from every page that loads it): it
 * tries the native OS dialog via /api/tools/select-folder and falls back to a
 * server-side directory browser over /api/tools/list-dirs when the server has
 * no dialog -- which is every build without the `native-dialog` Rust feature.
 *
 * `onSelect` fires only when a folder was actually chosen; a cancelled dialog
 * calls nothing. Returns false when the page forgot to load the script, so the
 * caller can show its own "enter the path manually" message instead of leaving
 * a dead button.
 */
type PickFolderFn = (initial: string, onSelect: (path: string) => void) => void;

export function pickFolder(initial: string, onSelect: (path: string) => void): boolean {
  const fn = (window as unknown as { pickFolder?: PickFolderFn }).pickFolder;
  if (typeof fn !== 'function') return false;
  fn(initial, onSelect);
  return true;
}
