// ESLint flat config for the browser TypeScript under `src/ts` and `e2e`.
//
// Scope deliberately mirrors tsconfig.json's `include`. `ui/default/static/dist`
// is build output and `ui/**` is excluded there too; linting generated bundles
// would measure esbuild's choices, not ours.
//
// The rule set is not "everything eslint offers". It is the rules whose failure
// mode this codebase has actually been bitten by, kept small enough that the
// ratchet counts mean something. `scripts/internal/eslint_ratchet.py` decides
// which of them are counted-with-a-backlog and which are hard errors; this file
// only has to make them *report*, so every gated rule is set to "warn" here and
// the ratchet applies severity itself.

import js from '@eslint/js';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    // Build output, dependencies, and the sample UI themes, which are not ours
    // to lint. Listed first: in flat config a global `ignores` block only
    // applies globally when it is the sole key in the object.
    ignores: [
      'node_modules/**',
      'ui/**',
      'src-tauri/**',
      'crates/**',
      '**/*.d.ts',
      'build.mjs',
      'eslint.config.mjs',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  {
    languageOptions: {
      parserOptions: {
        // Type-aware linting: without this the promise rules below cannot see
        // that a call returns a Promise, and they silently never fire -- which
        // would look exactly like a clean codebase.
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // A fetch whose promise is dropped swallows both the response and the
      // failure. This project's own history is full of "the request never
      // happened and nothing said so".
      '@typescript-eslint/no-floating-promises': 'warn',
      // An async function passed where a void callback is expected: the
      // rejection has nowhere to go.
      '@typescript-eslint/no-misused-promises': 'warn',
      '@typescript-eslint/await-thenable': 'warn',
      // `==` against null/undefined/0/'' is how a legitimate 0 or empty string
      // becomes "missing" -- the same shape as the sentinel bugs already
      // recorded in TODO.md.
      eqeqeq: ['warn', 'always', { null: 'ignore' }],
      // An unused binding is usually the remains of something that was renamed
      // or removed, i.e. a half-finished edit.
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },
  {
    // Vitest and Playwright specs: assertions and fixtures legitimately do
    // things production code should not.
    files: ['**/*.test.ts', '**/*.spec.ts', 'e2e/**/*.ts'],
    rules: {
      '@typescript-eslint/no-floating-promises': 'off',
      '@typescript-eslint/no-unsafe-assignment': 'off',
      '@typescript-eslint/no-unsafe-member-access': 'off',
    },
  },
);
