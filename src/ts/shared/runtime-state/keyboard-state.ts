let _keyboardPowerActive = false;

export function setKeyboardPowerActive(value: boolean): void {
  _keyboardPowerActive = value;
}

export function isKeyboardPowerActive(): boolean {
  return _keyboardPowerActive;
}
