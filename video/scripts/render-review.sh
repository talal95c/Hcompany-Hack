#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
ref="${1:?Pass the supplied main reference MP4 path}"
out="$root/out"
ffmpeg -y -hide_banner -loglevel error -i "$out/rio-launch.mp4" -vf 'fps=1,scale=480:-1,tile=6x7' -frames:v 1 "$out/sheet.png"
ffmpeg -y -hide_banner -loglevel error -i "$out/rio-launch.mp4" -vf "select='eq(n,170)+eq(n,905)+eq(n,2045)+eq(n,2235)+eq(n,2420)',scale=640:-1,tile=1x5:color=white" -frames:v 1 "$out/rio-style-column.png"
ffmpeg -y -hide_banner -loglevel error -i "$ref" -vf "fps=1,select='eq(n,0)+eq(n,11)+eq(n,19)+eq(n,22)+eq(n,28)',scale=640:-1,tile=1x5:color=white" -frames:v 1 "$out/reference-style-column.png"
ffmpeg -y -hide_banner -loglevel error -i "$out/reference-style-column.png" -i "$out/rio-style-column.png" -filter_complex "hstack,pad=iw:ih+52:0:52:color=white,drawtext=text='REFERENCE':x=24:y=16:fontsize=20:fontcolor=0x8a8a8a,drawtext=text='RIO':x=664:y=16:fontsize=20:fontcolor=0x8a8a8a" -frames:v 1 "$out/style-comparison.png"
printf 'Review artifacts: out/sheet.png, out/style-comparison.png\n'
