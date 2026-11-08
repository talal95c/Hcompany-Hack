#!/usr/bin/env bash
# An isolated worktree to change the harness without restarting the running
# dev app (`npm run tauri dev` rebuilds on every change under src-tauri/ or src/).
# Usage: worktree.sh <new-branch> [base-ref]
# Creates ../rio-wt-<branch> next to the repository, clones the build cache
# (APFS copy-on-write on macOS, so it is fast and small), and links .env and dist/.
set -euo pipefail
branch="${1:?usage: worktree.sh <new-branch> [base-ref]}"
base="${2:-HEAD}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
htutor="$(cd "$here/../../../../.." && pwd)"
top="$(git -C "$htutor" rev-parse --show-toplevel)"
prefix="$(python3 -c 'import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))' "$htutor" "$top")"
dest="$(dirname "$top")/rio-wt-${branch//\//-}"
git -C "$top" worktree add -b "$branch" "$dest" "$base"
wt="$dest/$prefix"; [ "$prefix" = "." ] && wt="$dest"
if [ -d "$htutor/src-tauri/target" ]; then
  cp -c -R "$htutor/src-tauri/target" "$wt/src-tauri/target" 2>/dev/null || cp -R "$htutor/src-tauri/target" "$wt/src-tauri/target"
fi
[ -f "$htutor/.env" ] && ln -sf "$htutor/.env" "$wt/.env"
[ -d "$htutor/dist" ] && ln -sfn "$htutor/dist" "$wt/dist"
echo "Worktree: $wt (branch $branch from $base)"
echo "Gates:    $here/check.sh $wt"
echo "Remove:   git -C $top worktree remove --force $dest"
