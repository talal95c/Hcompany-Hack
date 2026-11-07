#!/usr/bin/env sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cargo build --manifest-path "$HERE/src-tauri/Cargo.toml" --release --locked
exec "${CARGO_TARGET_DIR:-$HERE/src-tauri/target}/release/hcompany-desktop" "$@"
