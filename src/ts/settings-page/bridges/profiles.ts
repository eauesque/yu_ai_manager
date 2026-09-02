import {
  renderProfileManager,
  showCreateProfileDialog,
  duplicateProfile,
  renameProfile,
  deleteProfile,
  toggleProfileFavorite,
  exportProfileQR,
  showImportProfileDialog,
} from '../profiles';

export function createSettingsProfilesBridgeSection() {
  return {
    renderProfileManager,
    showCreateProfileDialog,
    duplicateProfile,
    renameProfile,
    deleteProfile,
    toggleProfileFavorite,
    exportProfileQR,
    showImportProfileDialog,
  };
}
