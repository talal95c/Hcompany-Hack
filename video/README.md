# Rio launch film

Remotion **4.0.540**, React 19, Inter. Composition **RioLaunch**, **1920×1080**, **60 fps**, **2473 frames / 41.217 s**.

The replacement art direction follows the supplied Motionfly launch reference: white space, regular/medium typography, word-by-word typing, bracket marks, depth-of-field app dock, brief dark introduction, pastel tiled room, gradient-edged prompt, checklist, turning laptop, orbit ring, floating tags, and restrained end card. Rio's orange → coral → pink replaces the reference's purple accent. No old grey/warm-gradient Act scenes remain.

## Run

```sh
cd video
npm ci
npx remotion browser ensure
# Supply the authorized recording at public/audio/loser.mp3 first.
npm run studio
npm run typecheck
npm run verify:beats
npm run render
ffmpeg -y -i out/rio-launch.mp4 -vf "fps=1,scale=480:-1,tile=6x7" -frames:v 1 out/sheet.png
ffmpeg -hide_banner -nostats -i out/rio-launch.mp4 -af ebur128=peak=true:framelog=verbose -f null -
```

`out/`, `node_modules/` and `public/audio/loser.mp3` are ignored. The rendered MP4 includes copyrighted audio and is **not cleared for public distribution**. Obtain the appropriate synchronization/master permissions before publication. No public deployment is performed by this project.

## Music and analysis

User-supplied **Tame Impala — Loser** (`~/ref/song.mp3`, 223.086 s decoded). The original is copied locally, not committed. `scripts/fetch-music.sh` documents the requested yt-dlp command; execute only if authorized to download the recording. No recording is downloaded by installation or analysis.

Selected source interval: **2.043356–43.258776 s**. Frames are rounded at 60 fps, so the rendered interval starts at source **2.050 s**; quantization is under one frame. Music enters over 32 frames, then fades over frames 2378–2443; the final 30 frames are silent.

`python3 scripts/analyze-music.py` requires local Python packages **librosa** and **numpy**. It emits `src/beats.json`, including source/segment beat times, onset strengths, scene starts, named cues and candidate downbeat frames. The librosa tracker reports 161.499 BPM due to discrete lag quantization; regression across steady tracked beats at source 12–80 s resolves **166.0022 BPM / 83.0011 half-time**. We retain the actual tracked times, not a synthetic uniform grid.

The source **10.704399 s** entrance is the reveal/drop at composition frame **520**. HPSS inspection of the source shows percussive RMS rising from **0.042 (10–11 s)** to **0.161 (11–12 s)**, alongside a strong onset at 10.704 s. The preceding source 2–10 s is relatively sparse. Candidate four-beat bar phase is anchored to this entrance; **this is not a learned/confirmed downbeat classification**. The black icon lead-in begins at frame 476; white gradient “Introducing” lands exactly at frame 520.

Every scene start and named tick/click/photo change is snapped to a tracked beat. Typing chunks and orbit pops choose the nearest beat/onset from the JSON. Letter movement, cursor travel, spring settling and caret blinking remain smooth frame-driven motion between these cues. `scripts/verify-beats.mjs` validates contiguous coverage, event membership and consent-before-execution, and prints the scene/beat comparison.

| Scene | Start frame | Content |
|---|---:|---|
| Hook | 0 | Brackets, One tutorial. Twelve Alt+Tabs. |
| Dock | 196 | Blurred hill, accelerating app switching, Pause. Rewind. Lost. |
| Introducing | 476 | Black R icon; drop at 520; rolling Rio lockup |
| Prompt | 694 | Pastel room dissolves, tutorial URL, Blender, send click |
| Checklist | 999 | Four beat-timed generation checks |
| Device | 1172 | CSS 3D laptop, real Blender guidance recording with click-following zoom |
| Ask | 1475 | Voice waveform, Why Base Color?, readable answer |
| Autopilot | 1735 | Explicit Yes, three ticks, recorded Blender cube turning blue |
| Orbit | 1952 | Twenty real icons/photo cards orbit in perspective |
| Claim | 2125 | Learn any software., typed subline, four pointer tags |
| End | 2299 | Rolling lockup, dark Try Rio for free pill, URL |

## Assets and audio mix

Brand files from `brand/`, photos from `docs/photos/`, app icons from `src/assets/apps/`, copied to `public/`. Device and Autopilot now use **real Blender 4.5.9 screen recordings**, not screenshots or a simulated cube. The white tutorial/voice/consent panels and the overlaid Rio notch/cursor are motion-design representations of Rio's interaction, rather than captures of Rio executing those actions.

## Blender recordings

`public/rec/device.mp4` and `autopilot.mp4` are 1920×1080 / 60 fps H.264 recordings, under 2 MB combined, so they are committed. The corresponding `*-cursor.json` files contain capture-clock timestamps, cursor samples and click coordinates. Autopilot also stores the measured first blue viewport frame as `blueTime`.

Regenerate on Linux with `/opt/blender/blender`, Xvfb, xdotool, xdpyinfo, Python 3 and ffmpeg/ffprobe:

```sh
bash scripts/record-blender.sh
node scripts/verify-recordings.mjs
```

The script uses dedicated display `:5`, software OpenGL and a private `$HOME/rio-recording/runtime`; it only terminates processes it starts. Do not run it while another application is using `:5`. `blender-recording-setup.py` disables the splash and tooltips, warms Material Preview, clears cube materials and leaves Properties visible. `drive-blender.py` drives many eased xdotool moves per second and records Material Properties → New → Base Color → vivid blue (`#3B82F6`) → dismiss picker. Device is the guidance portion of the same genuine capture; Autopilot includes the blue ending. Shader compilation is allowed to settle before the Base Color click. Regeneration replaces clips/logs together; rerun the checks and render afterward.

`BlenderRecording.tsx` embeds `OffthreadVideo` inside the unchanged laptop. Piecewise source retiming keeps Device's Base Color click at frame **1324**, consent at **1821**, and the recorded blue frame at **1886**, without changing `beats.json`. The intermediate New/hex-field micro-clicks use half-beat subdivisions between the existing Autopilot ticks. Nothing executes before Yes; the source holds at its first frame until consent + 8 frames.

`recording-motion.ts` precomputes a deterministic 120 Hz damped spring, carrying position/velocity across click targets. It anticipates each click by 14 frames, zooms toward 2×, clamps the camera within the recording and eases back out. The source OS cursor is excluded with `-draw_mouse 0`; the existing orange Rio cursor/ripple follows interpolated logged coordinates in the same camera space. A fixed Rio notch/step chip remains readable above the footage. A small velocity-dependent blur softens fast zooms. The Cap implementation's continuous spring/edge-constrained focus was reviewed; no Cap code or dependency is included.

`verify-recordings.mjs` checks cursor interpolation, bounded/smooth zoom, deterministic seeking, empty/error inputs, stream dimensions/rate, black frames, cursor jumps and the actual blue viewport pixels. Its mpdecimate count includes intentional static UI holds (the recorded OS cursor is hidden); it is not a count of missed cursor frames. Cursor and zoom animation are generated at the composition's 60 fps from the logs. Real-recording path used; no pure-Remotion fallback.

The copyrighted music dominates at gain 0.5; UI sounds are intentionally quiet. Mixkit SFX ([license](https://mixkit.co/license/#sfxFree)):

| ID | Sound | Gain |
|---|---|---:|
| 1386 | Keyboard typing | 0.035 |
| 275 | Fast double click on mouse | 0.10 |
| 1492 | Cinematic whoosh fast transition | 0.055 |

Sources: `https://assets.mixkit.co/active_storage/sfx/<id>/<id>-preview.mp3`. Old Mixkit music and unused SFX were removed. Output H.264 uses CRF 16, AAC audio. `out/render.log` records the local render; `out/loudness.log` records EBU R128 measurement.

## Review artifacts (local, ignored)

- `out/rio-launch.mp4` — final full-length render.
- `out/sheet.png` — requested one-frame-per-second 6×7 contact sheet.
- `out/style-comparison.png` — supplied reference on the left, Rio on the right, matched hook/prompt/orbit/claim/end-card grammar.
- `out/beat-verification.txt` — scene starts, internal reveal cuts and nearest beats.
- `out/blender-sheet.png` — frames 1150–2000 sampled at 4 fps after the recording replacement.
- `out/recording-verification.txt` — spring/cursor tests, raw recording frame counts and blue-pixel validation.

Generate both sheets with `bash scripts/render-review.sh /path/to/main-reference.mp4`. The unused final cell of the 6×7 sheet is black; it is not a video frame. Final measured mix: **−14.0 LUFS integrated**, **4.9 LU LRA**, **−4.6 dBFS true peak**. Video stream: **2473 frames / 41.216667 s**; the AAC container has approximately 20 ms encoder padding. TypeScript and beat/cue verification are clean. Contact sheet and side-by-side stills were visually inspected; subjective audio listening and full-motion playback were not performed.

Reference contact sheets are kept outside the repo at `~/ref/motionfly-sheet.png` and `~/ref/secondary-sheet.png`. Remotion and HyperFrames skills were reread for deterministic typing, sequencing, 3D transforms and audio timing; this is a Remotion implementation, not a HyperFrames runtime project. Older Act 1/2 exports in `out/` are stale and do not represent this rebuild.
