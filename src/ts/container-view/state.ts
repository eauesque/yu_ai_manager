/**
 * container-view/state.ts — ContainerView panel state management.
 */

export interface ContainerViewState {
  isOpen: boolean;
  containerType: 'zip' | 'folder' | '';
  containerKey: string;
  containerPath: string;
  memberIds: number[];
  focusFileId: number | null;
}

let _state: ContainerViewState = {
  isOpen: false,
  containerType: '',
  containerKey: '',
  containerPath: '',
  memberIds: [],
  focusFileId: null,
};

export function getState(): Readonly<ContainerViewState> {
  return _state;
}

export function setState(partial: Partial<ContainerViewState>): void {
  _state = { ..._state, ...partial };
}

export function resetState(): void {
  _state = {
    isOpen: false,
    containerType: '',
    containerKey: '',
    containerPath: '',
    memberIds: [],
    focusFileId: null,
  };
}

export function isContainerViewOpen(): boolean {
  return _state.isOpen;
}
