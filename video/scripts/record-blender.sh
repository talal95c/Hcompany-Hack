#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${RIO_CAPTURE_WORK:-$HOME/rio-recording}"
mkdir -p "$WORK/runtime" "$ROOT/public/rec"
chmod 700 "$WORK/runtime"
export DISPLAY=:5 LIBGL_ALWAYS_SOFTWARE=1 XDG_RUNTIME_DIR="$WORK/runtime"
export RIO_CAPTURE_READY="$WORK/ready-$$"
XVFB_PID=''
cleanup() {
  kill "$BLENDER_PID" ${XVFB_PID:+"$XVFB_PID"} 2>/dev/null || true
  rm -f "$RIO_CAPTURE_READY"
}
if ! xdpyinfo -display :5 >/dev/null 2>&1; then
  Xvfb :5 -screen 0 1920x1080x24 -nolisten tcp > "$WORK/xvfb.log" 2>&1 &
  XVFB_PID=$!
fi
python3 -c 'import subprocess,time
for attempt in range(100):
    if subprocess.run(["xdpyinfo","-display",":5"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:
        break
    time.sleep(.05)
else:
    raise RuntimeError("Xvfb :5 did not become ready")'
/opt/blender/blender --factory-startup --gpu-backend opengl --window-geometry 0 0 1920 1080 --python "$ROOT/scripts/blender-recording-setup.py" > "$WORK/blender.log" 2>&1 &
BLENDER_PID=$!
trap cleanup EXIT
python3 "$ROOT/scripts/drive-blender.py" "$BLENDER_PID" "$WORK" "$ROOT/public/rec"
