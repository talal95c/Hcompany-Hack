import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

pid, work, output = sys.argv[1:]
work, output = Path(work), Path(output)

def xdo(*args):
    return subprocess.check_output(['xdotool', *map(str, args)], text=True).strip()

deadline = time.monotonic() + 180
while not Path(os.environ['RIO_CAPTURE_READY']).exists():
    if time.monotonic() > deadline:
        raise RuntimeError('Blender did not become ready; inspect blender.log')
    os.kill(int(pid), 0)
    time.sleep(.1)

window = xdo('search', '--pid', pid).splitlines()[-1]
xdo('windowfocus', '--sync', window)
xdo('mousemove', '--sync', 1050, 430)
log = (work / 'capture.log').open('w')
capture = subprocess.Popen([
    'ffmpeg', '-y', '-hide_banner', '-f', 'x11grab', '-draw_mouse', '0',
    '-framerate', '60', '-video_size', '1920x1080', '-i', ':5',
    '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18',
    '-pix_fmt', 'yuv420p', str(work / 'master.mp4'),
], stdout=log, stderr=log)
deadline = time.monotonic() + 15
while 'frame=' not in (work / 'capture.log').read_text():
    if capture.poll() is not None or time.monotonic() > deadline:
        raise RuntimeError('x11grab did not start; inspect capture.log')
    time.sleep(.01)

capture_epoch = float(re.search(r'start: ([0-9.]+)', (work / 'capture.log').read_text()).group(1))
start = time.monotonic() - (time.time() - capture_epoch)
samples = []
clicks = []
position = [1050, 430]

def sample():
    samples.append({'time': round(time.monotonic() - start, 5), 'x': position[0], 'y': position[1]})

def hold(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        sample()
        time.sleep(1 / 60)

def glide(x, y, seconds):
    origin = position.copy()
    then = time.monotonic()
    for step in range(1, round(seconds * 60) + 1):
        p = step / round(seconds * 60)
        p = p * p * (3 - 2 * p)
        position[:] = [round(origin[0] + (x - origin[0]) * p), round(origin[1] + (y - origin[1]) * p)]
        xdo('mousemove', '--sync', *position)
        sample()
        time.sleep(max(0, then + step / 60 - time.monotonic()))

def click(label):
    clicks.append({'time': round(time.monotonic() - start, 5), 'x': position[0], 'y': position[1], 'label': label})
    xdo('mousedown', '1')
    time.sleep(.12)
    xdo('mouseup', '1')

try:
    sample()
    hold(.4)
    glide(1605, 810, 1.2)
    click('Material Properties')
    hold(1.1)
    glide(1795, 530, .7)
    click('New material')
    hold(4)
    glide(1815, 660, .8)
    click('Base Color')
    hold(1.2)
    device_end = time.monotonic() - start
    glide(1770, 631, .4)
    click('Vivid blue')
    xdo('key', 'ctrl+a')
    xdo('type', '--clearmodifiers', '--delay', '35', '3B82F6')
    xdo('key', 'Return')
    hold(.5)
    glide(1645, 680, .35)
    click('Apply')
    glide(1030, 470, 1)
    hold(2.5)
finally:
    capture.send_signal(signal.SIGINT)
    capture.wait(timeout=30)
    log.close()

pixels = subprocess.check_output([
    'ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(work / 'master.mp4'),
    '-vf', 'crop=64:64:760:450,scale=1:1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-',
])
blue_frame = next((i // 3 for i in range(0, len(pixels), 3) if pixels[i + 2] > pixels[i] * 1.3), None)
if blue_frame is None:
    raise RuntimeError('The recorded viewport never turned blue; inspect master.mp4')

for name, end in [('device', device_end), ('autopilot', time.monotonic() - start)]:
    subprocess.run([
        'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', str(work / 'master.mp4'),
        '-t', str(end), '-an', '-c:v', 'libx264', '-preset', 'slow', '-crf', '18',
        '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output / f'{name}.mp4'),
    ], check=True)
    duration = float(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(output / f'{name}.mp4'),
    ], text=True))
    data = {'width': 1920, 'height': 1080, 'fps': 60, 'duration': duration,
            'samples': [s for s in samples if s['time'] <= end],
            'clicks': [c for c in clicks if c['time'] <= end]}
    if name == 'autopilot':
        data['blueTime'] = blue_frame / 60
    (output / f'{name}-cursor.json').write_text(json.dumps(data, separators=(',', ':')) + '\n')
    print(f'{name}: {duration:.3f}s, {len(data["samples"])} cursor samples, {len(data["clicks"])} clicks')
