/**
 * Minimal type declarations for nspell (no official @types package).
 * nspell is a pure-JS Hunspell reimplementation (MIT licence).
 */
declare module 'nspell' {
  interface Dictionary {
    aff: string | Buffer;
    dic?: string | Buffer;
  }

  interface NSpell {
    /** Returns true if `word` is spelled correctly. */
    correct(word: string): boolean;
    /** Returns an array of suggested corrections for a misspelled `word`. */
    suggest(word: string): string[];
    /** Adds a word to the personal dictionary. */
    add(word: string, model?: string): this;
    /** Removes a word from the personal dictionary. */
    remove(word: string): this;
  }

  /**
   * Create a new spell checker instance.
   * @param aff Affix document string (or an object with `aff` and optional `dic`)
   * @param dic Dictionary document string (when passing aff/dic separately)
   */
  function nspell(aff: string | Dictionary | Dictionary[], dic?: string): NSpell;

  export = nspell;
}
