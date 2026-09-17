/**
 * prompt-library.ts -- Re-export barrel for Prompt Library bridge integration.
 * Split into prompt-library-picker.ts (picker/save modals)
 * and prompt-library-attach.ts (toolbar attach helper).
 */

export type { CharacterEntry } from './prompt-library-picker';
export type { PromptLibraryAttachConfig } from './prompt-library-attach';
export { BridgePromptLibrary } from './prompt-library-attach';
