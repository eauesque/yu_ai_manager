#!/usr/bin/env bash
# Fetch the prebuilt PDFium shared library used for PDF thumbnail rendering.
#
# Why a fetch script rather than a vendored binary: libpdfium.so is ~7.3 MB per
# platform, and `*.so` is already gitignored. The release build and CI call this
# script; a developer without it still gets a working server -- the PDF thumbnail
# path degrades to a placeholder image, exactly as Python does when poppler is
# absent (core/files_core/media_placeholders.py::pdf_placeholder).
#
# Licensing: the binaries come from bblanchon/pdfium-binaries. Its build scripts
# are MIT; the library itself is Google's PDFium under BSD-3-Clause. Neither is
# GPL/LGPL/AGPL, so both may be redistributed with this project. The archive's
# own LICENSE file is copied next to the library.
#
# The release is pinned and the download checksummed: an unpinned fetch would let
# the bytes we ship change without a commit.
set -euo pipefail

PDFIUM_RELEASE="chromium/8009"          # PDFium 153.0.8009.0
PDFIUM_SHA256_LINUX_X64="be513e8021a5bf8eb2116e00d78c3bacb82c5a02b3785156ae14fe5e33084385"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dest="${repo_root}/vendor/pdfium/linux-x64"
tarball="pdfium-linux-x64.tgz"

if [ -f "${dest}/libpdfium.so" ]; then
    echo "pdfium: already present at ${dest}/libpdfium.so"
    exit 0
fi

tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT

echo "pdfium: downloading ${PDFIUM_RELEASE} ${tarball}"
gh release download "${PDFIUM_RELEASE}" \
    --repo bblanchon/pdfium-binaries \
    --pattern "${tarball}" \
    --dir "${tmp}"

echo "${PDFIUM_SHA256_LINUX_X64}  ${tmp}/${tarball}" | sha256sum --check --status \
    || { echo "pdfium: checksum mismatch -- refusing to install" >&2; exit 1; }

tar xzf "${tmp}/${tarball}" -C "${tmp}"
mkdir -p "${dest}"
cp "${tmp}/lib/libpdfium.so" "${dest}/libpdfium.so"
cp "${tmp}/LICENSE" "${dest}/LICENSE"

echo "pdfium: installed ${dest}/libpdfium.so"
