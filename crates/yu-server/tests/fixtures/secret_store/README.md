# secret_store test fixture

**These keys protect nothing. They exist so a test can prove Rust and Python
agree on the encrypted-secret format.**

| File | What it is |
|---|---|
| `data/secret.key` | Legacy single-key file (Fernet). Used by the `enc:<token>` path. |
| `data/keyring.json` | Keyring for the `enc:v2:<key_id>:<token>` path. Holds one key, id `k_fixture0000test`. |

The tests in `src/secret_store.rs` encrypt and decrypt the literal strings
`python-fixture-secret` and `rust-to-python-secret` against this fixture. That
is the entire threat surface: publishing these keys reveals two strings that are
already written in the test source next to them.

They were committed deliberately. Before that, `.gitignore` swallowed them via
its blanket `data/` and `*.key` rules, so the fixture referenced key material
that was never in the repository — the test could not pass on a fresh clone, on
any machine. Two negation rules now keep them tracked (gitignore's later rules
win, so one negation was not enough).

## Regenerating

`scripts/internal/gen_secret_store_fixture.py` in the upstream repository
rewrites both files and the expected tokens. It pins the key id, clears
`YU_SECRET_PASSPHRASE` first (leaving it set derives the key from the passphrase
instead, producing a fixture nobody else can decrypt), and self-checks that
Python can read back what it just wrote.

The test reads the key id out of `tokens.json` rather than pinning it, so
regenerating does not require touching the test.
