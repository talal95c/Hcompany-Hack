#!/usr/bin/env bash
set -euo pipefail
WORK=$1
trap 'kill ${CALC_PID:-} ${BUS_PID:-} ${XVFB_PID:-} 2>/dev/null || true' EXIT
Xvfb -displayfd 3 -screen 0 1280x900x24 -nolisten tcp 3>"$WORK/display" >"$WORK/xvfb.log" 2>&1 &
XVFB_PID=$!
for i in {1..100}; do [[ -s "$WORK/display" ]] && break; sleep 0.1; done
export DISPLAY=:$(<"$WORK/display")
export GTK_MODULES=gail:atk-bridge SAL_USE_VCLPLUGIN=gtk3 NO_AT_BRIDGE=0
unset AT_SPI_BUS_ADDRESS
"$AT_SPI_LAUNCHER" --launch-immediately >"$WORK/bus.log" 2>&1 &
BUS_PID=$!
soffice -env:UserInstallation="file://$WORK/converter" --headless --convert-to ods --outdir "$WORK" "$WORK/probe.csv" >"$WORK/convert.log" 2>&1
localc -env:UserInstallation="file://$WORK/profile" --norestore --nofirststartwizard "$WORK/probe.ods" >"$WORK/calc.log" 2>&1 &
CALC_PID=$!
WINDOW=$(timeout 25 xdotool search --sync --onlyvisible --name 'LibreOffice Calc' | head -n 1)
xdotool windowraise "$WINDOW"
xdotool windowfocus --sync "$WINDOW"
python3 - "$WORK" <<'PY'
import json
import os
import sys
from pathlib import Path

keys = ("DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "GTK_MODULES", "SAL_USE_VCLPLUGIN", "NO_AT_BRIDGE")
ready = Path(sys.argv[1], "ready.pending")
ready.write_text(json.dumps({k: os.environ[k] for k in keys}))
ready.rename(ready.with_name("ready.json"))
PY
read -r _ || true
