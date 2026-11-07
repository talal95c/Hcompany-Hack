#!/usr/bin/env bash
set -euo pipefail
runtime=$(mktemp -d)
export XDG_RUNTIME_DIR="$runtime/runtime"
mkdir -m 700 "$XDG_RUNTIME_DIR"
export DISPLAY="${GENERIC_DISPLAY:-:89}"
case "$DISPLAY" in :0|:77) echo 'Affichage réservé' >&2; exit 1;; esac
if [ -e "/tmp/.X${DISPLAY#:}-lock" ]; then
    echo 'Affichage déjà occupé' >&2
    exit 1
fi
export GTK_MODULES=gail:atk-bridge SAL_USE_VCLPLUGIN=gtk3 GNOME_ACCESSIBILITY=1
export GTK_USE_PORTAL=0 GIO_USE_VFS=local
export LANG=fr_FR.UTF-8 LANGUAGE=fr
Xvfb "$DISPLAY" -screen 0 1600x1000x24 >"$runtime/display.log" 2>&1 &
display_pid=$!
trap 'kill "$display_pid" 2>/dev/null || true; rm -rf "$runtime"' EXIT
/usr/libexec/at-spi-bus-launcher --launch-immediately >"$runtime/bus.log" 2>&1 &
export LESSON_PROFILE="$runtime/profile"
for attempt in $(seq 1 50); do
    if xdotool getdisplaygeometry >/dev/null 2>&1; then break; fi
    sleep 0.1
done
if [ "${1:-}" = "--discover" ]; then
    shift
    /usr/bin/python3 "$(dirname "$0")/discover_native.py" "$@"
else
    /usr/bin/python3 "$(dirname "$0")/a11y_harness.py" "$@"
fi
