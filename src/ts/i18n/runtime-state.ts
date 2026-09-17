/**
 * i18n runtime state — shared dictionary/runtime flags without browser globals.
 */

type FlatDict = Record<string, string>;
type RuntimeDict = Record<string, unknown>;

let _lang = 'en';
let _flatDict: FlatDict = {};
let _runtimeDict: RuntimeDict = {};
let _runtimeLoaded = false;

export function setI18nDictionary(lang: string, dict: FlatDict): void {
  _lang = lang;
  _flatDict = dict || {};
}

export function getI18nLanguage(): string {
  return _lang;
}

export function getI18nDictionary(): FlatDict {
  return _flatDict;
}

export function setTrRuntimeDict(dict: RuntimeDict): void {
  _runtimeDict = dict || {};
}

export function getTrRuntimeDict(): RuntimeDict {
  return _runtimeDict;
}

export function setTrRuntimeLoaded(loaded: boolean): void {
  _runtimeLoaded = loaded;
}

export function isTrRuntimeLoaded(): boolean {
  return _runtimeLoaded;
}
