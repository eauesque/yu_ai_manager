/**
 * favorites/select.ts -- Re-export barrel for explorer-style selection.
 * Split into select-actions.ts (batch operations)
 * and select-init.ts (event delegation + rubber-band).
 */

export {
  favSelectToggle, favSelectChanged, favSelectAll, favDeselectAll,
  favBatchAdd, favBatchRemove, favShowCollDropdown,
  favBatchDownloadZip, favBatchAddToCollection,
} from './select-actions';
export { initFavSelect } from './select-init';
