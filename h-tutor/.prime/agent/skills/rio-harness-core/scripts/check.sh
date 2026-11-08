#!/usr/bin/env bash
# Gates for the harness core: rustfmt, clippy with no warning, unit tests.
# Usage: check.sh [h-tutor dir]   (default: the h-tutor this skill lives in)
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="${1:-$(cd "$here/../../../../.." && pwd)}"
cd "$root/src-tauri"
echo "== rustfmt";  cargo fmt --check
echo "== clippy";   cargo clippy --locked --all-targets -- -D warnings
echo "== tests";    cargo test --locked --lib 2>&1 | tail -3
