RAR test fixtures
=================

Source: https://github.com/muja/unrar.rs (`data/`), the upstream repository of the
`unrar` crate this code depends on. Licensed MIT OR Apache-2.0 with the rest of that
repository.

Vendored because a `.rar` cannot be produced here: RAR compression is proprietary, no
permissive Rust writer exists (writing one is precisely what the UnRAR licence forbids),
and no `rar` binary is installed. Generating fixtures locally is therefore not an option;
these are the upstream project's own known-content archives.

Contents, taken from unrar.rs's own tests (`tests/simple.rs`, `tests/utf8.rs`):

  version.rar   one entry `VERSION`, content exactly "unrar-0.4.0"
  unicode.rar   one entry named `te…―st✌`

`rar3-subdirs.rar` comes from a second source: https://github.com/markokr/rarfile
(`test/files/`, ISC licence), the test corpus of the Python library this code is
replacing. It is the only fixture available with **directory entries**, which the
other two lack. Contents per that repository's own `rar3-subdirs.rar.exp`:

  files        sub/dir1/file1.txt (6 bytes)
               sub/dir2/file2.txt (6 bytes)
               sub/with space/long fn.txt (8 bytes)
               sub/üȵĩöḋè/file.txt (5 bytes)
  directories  sub/  sub/dir1/  sub/dir2/  sub/empty/
               sub/with space/  sub/üȵĩöḋè/

It exists so the UnRAR directory flag is exercised for real rather than only through
a synthetic unit test: `empty` is a directory basename with no matching file, so a
request for it must resolve to nothing. Without the directory filter it would be a
candidate.

If you need a fixture shape none of these cover, say so rather than approximating it.
The size cap can be exercised against any of them by passing a small `max` to
`cached_rar_member` directly.
