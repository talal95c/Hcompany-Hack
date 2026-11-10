#!/usr/bin/env bash
set -euo pipefail
# Copyrighted recording: obtain permission for any publication or distribution.
# Optional yt-dlp acquisition, for users authorized to download the recording:
# python3 -m yt_dlp -x --audio-format mp3 https://www.youtube.com/watch?v=qmIo0F2uOGU
# The downloaded recording must never be committed; it is intentionally ignored.
root="$(cd "$(dirname "$0")/.." && pwd)"
python3 -m yt_dlp -x --audio-format mp3 -o "$root/public/audio/loser.%(ext)s" 'https://www.youtube.com/watch?v=qmIo0F2uOGU'
