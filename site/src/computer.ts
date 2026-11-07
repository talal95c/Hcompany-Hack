import {
  bounds,
  COLUMNS,
  GRID_X,
  GRID_Y,
  initialRect,
  ROWS,
  screenMesh,
  smoothstep,
  ZOOM_DURATION,
  zoomProgress,
  zoomRect,
  type Point,
} from "./crtGeometry";

export type Computer = {
  point: (x: number, y: number) => void;
  reset: () => void;
  hover: (active: boolean) => void;
  enter: (done: () => void) => boolean;
  cancel: () => void;
  dispose: () => void;
};
type Frame = {
  shell: HTMLCanvasElement;
  glass: HTMLImageElement;
  column: number;
  row: number;
};

function feather(image: HTMLImageElement) {
  const layer = document.createElement("canvas");
  layer.width = image.naturalWidth;
  layer.height = image.naturalHeight;
  const ctx = layer.getContext("2d");
  if (!ctx) throw new Error("Canvas unavailable");
  ctx.drawImage(image, 0, 0);
  ctx.globalCompositeOperation = "destination-in";
  for (const vertical of [false, true]) {
    const gradient = ctx.createLinearGradient(
      0,
      0,
      vertical ? 0 : layer.width,
      vertical ? layer.height : 0,
    );
    gradient.addColorStop(0, "transparent");
    gradient.addColorStop(0.12, "#000");
    gradient.addColorStop(0.88, "#000");
    gradient.addColorStop(1, "transparent");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, layer.width, layer.height);
  }
  return layer;
}

function preview() {
  const canvas = document.createElement("canvas");
  canvas.width = 960;
  canvas.height = 760;
  return canvas;
}

function drawPreview(
  canvas: HTMLCanvasElement,
  hover: boolean,
  burst: number,
  crt: number,
) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const { width: w, height: h } = canvas;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#f0f0f0";
  ctx.fillRect(0, 0, w, h);
  ctx.textAlign = "center";
  ctx.fillStyle = "#1a1a1a";
  ctx.font = "800 190px Inter, Arial, sans-serif";
  ctx.fillText("Rio", w / 2, h * 0.3);
  ctx.fillStyle = "#6f6f6f";
  ctx.font = "500 34px Inter, Arial, sans-serif";
  ctx.fillText("Learn any software.", w / 2, h * 0.8);
  ctx.fillStyle = "#ff7a1a";
  ctx.font = "500 22px 'Geist Mono', monospace";
  ctx.fillText("LIVE, ON YOUR SCREEN", w / 2, h * 0.87);
  ctx.save();
  ctx.translate(w / 2, h / 2);
  ctx.scale(1 + burst * 0.5, 1 + burst * 0.5);
  ctx.globalAlpha = 1 - burst;
  const layers = [
    [176, 91, 33],
    [166, 81, 27],
    [156, 71, 22],
    [151, 66, 19],
  ];
  layers.forEach(([x, y, radius], index) => {
    const dark = index % 2 === 0;
    ctx.fillStyle = dark !== hover ? "#000" : "#fff";
    ctx.beginPath();
    ctx.roundRect(-x, -y, x * 2, y * 2, radius);
    ctx.fill();
  });
  ctx.fillStyle = hover ? "#fff" : "#000";
  ctx.font = "bold 64px monospace";
  ctx.textBaseline = "middle";
  ctx.fillText(
    window.matchMedia("(pointer: coarse)").matches ? "Tap" : "Click",
    0,
    3,
  );
  ctx.restore();
  ctx.fillStyle = `rgba(0,0,0,${0.055 * crt})`;
  for (let y = 0; y < h; y += 6) ctx.fillRect(0, y, w, 1);
}

function triangle(
  ctx: CanvasRenderingContext2D,
  image: HTMLCanvasElement,
  p: Point[],
  rect: ReturnType<typeof initialRect>,
) {
  const [a, b, c] = p.map((point) => ({
    x: rect.x + point.x * rect.size,
    y: rect.y + point.y * rect.size,
    u: point.u * image.width,
    v: point.v * image.height,
  }));
  const d = a.u * (b.v - c.v) + b.u * (c.v - a.v) + c.u * (a.v - b.v);
  if (Math.abs(d) < 1e-9) return;
  ctx.save();
  ctx.beginPath();
  const center = { x: (a.x + b.x + c.x) / 3, y: (a.y + b.y + c.y) / 3 };
  const expanded = [a, b, c].map((point) => {
    const length = Math.hypot(point.x - center.x, point.y - center.y) || 1;
    return {
      x: point.x + ((point.x - center.x) / length) * 0.6,
      y: point.y + ((point.y - center.y) / length) * 0.6,
    };
  });
  ctx.moveTo(expanded[0].x, expanded[0].y);
  ctx.lineTo(expanded[1].x, expanded[1].y);
  ctx.lineTo(expanded[2].x, expanded[2].y);
  ctx.closePath();
  ctx.clip();
  ctx.transform(
    (a.x * (b.v - c.v) + b.x * (c.v - a.v) + c.x * (a.v - b.v)) / d,
    (a.y * (b.v - c.v) + b.y * (c.v - a.v) + c.y * (a.v - b.v)) / d,
    (a.x * (c.u - b.u) + b.x * (a.u - c.u) + c.x * (b.u - a.u)) / d,
    (a.y * (c.u - b.u) + b.y * (a.u - c.u) + c.y * (b.u - a.u)) / d,
    (a.x * (b.u * c.v - c.u * b.v) +
      b.x * (c.u * a.v - a.u * c.v) +
      c.x * (a.u * b.v - b.u * a.v)) /
      d,
    (a.y * (b.u * c.v - c.u * b.v) +
      b.y * (c.u * a.v - a.u * c.v) +
      c.y * (a.u * b.v - b.u * a.v)) /
      d,
  );
  ctx.drawImage(image, 0, 0);
  ctx.restore();
}

export function mountComputer(
  canvas: HTMLCanvasElement,
  onReady: (ready: boolean) => void,
): Computer {
  const ctx = canvas.getContext("2d", { alpha: true });
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const cache = new Map<string, Promise<Frame>>();
  const images = new Set<HTMLImageElement>();
  const picture = preview();
  let disposed = false,
    request = 0,
    frame: Frame | undefined;
  let desired = "1-9",
    pending = "",
    hover = false,
    dirty = true;
  let target = { x: 9, y: 1 };
  const position = { x: 9, y: 1 };
  let width = innerWidth,
    height = innerHeight,
    ratio = 1;
  let zoom: { start: number; done: () => void } | undefined;

  function resize() {
    width = innerWidth;
    height = innerHeight;
    ratio = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    dirty = true;
    schedule();
  }
  function load(column: number, row: number) {
    const key = `${row}-${column}`;
    desired = key;
    if (pending === key || (frame?.column === column && frame.row === row))
      return;
    pending = key;
    if (!cache.has(key)) {
      const image = (layer: string) =>
        new Promise<HTMLImageElement>((resolve, reject) => {
          const img = new Image();
          images.add(img);
          img.onload = () => {
            images.delete(img);
            resolve(img);
          };
          img.onerror = () => {
            images.delete(img);
            reject(new Error("Computer frame unavailable"));
          };
          img.src = `/crt/${layer}-${key}.webp`;
        });
      cache.set(
        key,
        Promise.all([image("case"), image("glass")]).then(([shell, glass]) => ({
          shell: feather(shell),
          glass,
          column,
          row,
        })),
      );
      if (cache.size > 8) cache.delete(cache.keys().next().value!);
    }
    void cache
      .get(key)!
      .then((value) => {
        if (disposed || desired !== key) return;
        pending = "";
        if (zoom) return;
        frame = value;
        dirty = true;
        onReady(true);
        schedule();
      })
      .catch(() => {
        cache.delete(key);
        if (desired === key) pending = "";
      });
  }
  function schedule() {
    if (!request && !disposed && !document.hidden && ctx)
      request = requestAnimationFrame(draw);
  }
  function draw(time: number) {
    request = 0;
    if (!ctx || disposed) return;
    position.x += (target.x - position.x) * 0.15;
    position.y += (target.y - position.y) * 0.15;
    const moving =
      Math.abs(target.x - position.x) + Math.abs(target.y - position.y) > 0.01;
    if (!zoom)
      load(
        Math.max(0, Math.min(COLUMNS - 1, Math.round(position.x))),
        Math.max(0, Math.min(ROWS - 1, Math.round(position.y))),
      );
    if (frame && (dirty || zoom)) {
      dirty = false;
      const progress = zoom
        ? Math.min(1, (time - zoom.start) / ZOOM_DURATION)
        : 0;
      const ease = zoomProgress(progress);
      const flat = smoothstep(0.1, 0.48, progress);
      const wall = 1 - smoothstep(0.45, 0.65, progress);
      const mesh = screenMesh(frame.column, frame.row);
      const box = bounds(mesh);
      const from = initialRect(width, height),
        to = zoomRect(mesh, width, height);
      const rect = {
        x: from.x + (to.x - from.x) * ease,
        y: from.y + (to.y - from.y) * ease,
        size: from.size + (to.size - from.size) * ease,
      };
      drawPreview(
        picture,
        hover,
        smoothstep(0, 0.2, progress),
        1 - smoothstep(0.15, 0.55, progress),
      );
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.clearRect(0, 0, width, height);
      ctx.filter = "none";
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-over";
      const points = mesh.map((point) => ({
        ...point,
        x: point.x * (1 - flat) + (box.x + point.u * box.width) * flat,
        y: point.y * (1 - flat) + (box.y + point.v * box.height) * flat,
      }));
      if (flat >= 1) {
        ctx.drawImage(
          picture,
          rect.x + box.x * rect.size,
          rect.y + box.y * rect.size,
          box.width * rect.size,
          box.height * rect.size,
        );
      } else {
        for (let y = 0; y < GRID_Y; y++)
          for (let x = 0; x < GRID_X; x++) {
            const a = y * (GRID_X + 1) + x,
              b = a + 1,
              c = a + GRID_X + 1,
              d = c + 1;
            triangle(ctx, picture, [points[a], points[b], points[c]], rect);
            triangle(ctx, picture, [points[b], points[d], points[c]], rect);
          }
      }
      ctx.save();
      ctx.beginPath();
      const outline = [
        ...Array.from({ length: GRID_X + 1 }, (_, x) => x),
        ...Array.from(
          { length: GRID_Y },
          (_, y) => (y + 1) * (GRID_X + 1) + GRID_X,
        ),
        ...Array.from(
          { length: GRID_X },
          (_, x) => GRID_Y * (GRID_X + 1) + GRID_X - x - 1,
        ),
        ...Array.from(
          { length: GRID_Y - 1 },
          (_, y) => (GRID_Y - y - 1) * (GRID_X + 1),
        ),
      ];
      outline.forEach((index, i) => {
        const point = points[index];
        const x = rect.x + point.x * rect.size,
          y = rect.y + point.y * rect.size;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.closePath();
      ctx.clip();
      ctx.globalCompositeOperation = "screen";
      ctx.globalAlpha = 0.4 * (1 - flat);
      ctx.drawImage(frame.glass, rect.x, rect.y, rect.size, rect.size);
      ctx.restore();
      ctx.globalCompositeOperation = "source-over";
      ctx.globalAlpha = wall;
      ctx.filter = "saturate(1.6) hue-rotate(6deg)";
      ctx.drawImage(frame.shell, rect.x, rect.y, rect.size, rect.size);
      ctx.filter = "none";
      ctx.globalAlpha = 1;
      if (progress >= 1 && zoom) {
        const done = zoom.done;
        zoom = undefined;
        done();
        return;
      }
    }
    if (zoom || moving) schedule();
  }
  const visibility = () => {
    if (document.hidden) {
      cancelAnimationFrame(request);
      request = 0;
    } else {
      dirty = true;
      schedule();
    }
  };
  const cancel = () => {
    zoom = undefined;
    dirty = true;
    schedule();
  };
  const reset = () => {
    target = { x: 9, y: 1 };
    schedule();
  };
  const changedMotion = () => {
    reset();
    if (motion.matches && zoom) {
      const done = zoom.done;
      zoom = undefined;
      done();
    }
  };
  if (ctx) {
    resize();
    load(9, 1);
  }
  window.addEventListener("resize", resize);
  document.addEventListener("visibilitychange", visibility);
  motion.addEventListener("change", changedMotion);
  return {
    point(x, y) {
      if (
        zoom ||
        motion.matches ||
        window.matchMedia("(pointer: coarse)").matches
      )
        return;
      target = {
        x: 9 + Math.tanh((x - width / 2) / (width * 0.4)) * 9,
        y: 1 - Math.tanh((y - height / 2) / (height * 0.4)),
      };
      schedule();
    },
    reset,
    hover(active) {
      hover = active;
      dirty = true;
      schedule();
    },
    enter(done) {
      if (!ctx || !frame || motion.matches || disposed) return false;
      if (!zoom) {
        zoom = { start: performance.now(), done };
        schedule();
      }
      return true;
    },
    cancel,
    dispose() {
      disposed = true;
      zoom = undefined;
      cancelAnimationFrame(request);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", visibility);
      motion.removeEventListener("change", changedMotion);
      for (const img of images) {
        img.onload = null;
        img.onerror = null;
        img.src = "";
      }
      images.clear();
      cache.clear();
    },
  };
}
