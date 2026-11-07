import { beforeEach, describe, expect, it, vi } from "vitest";
import { mountComputer } from "../src/computer";
import { ZOOM_DURATION } from "../src/crtGeometry";

let callbacks: Map<number, FrameRequestCallback>;
let nextId: number;
let ctx: CanvasRenderingContext2D;

function tick(time: number) {
  const current = [...callbacks.values()];
  callbacks.clear();
  current.forEach((callback) => callback(time));
}

async function loaded() {
  for (let i = 0; i < 6; i++) await Promise.resolve();
}

beforeEach(() => {
  callbacks = new Map();
  nextId = 0;
  vi.stubGlobal(
    "requestAnimationFrame",
    vi.fn((callback: FrameRequestCallback) => {
      const id = ++nextId;
      callbacks.set(id, callback);
      return id;
    }),
  );
  vi.stubGlobal(
    "cancelAnimationFrame",
    vi.fn((id: number) => callbacks.delete(id)),
  );
  vi.spyOn(performance, "now").mockReturnValue(0);
  const methods = [
    "clearRect",
    "fillRect",
    "fillText",
    "stroke",
    "roundRect",
    "fill",
    "save",
    "restore",
    "translate",
    "scale",
    "beginPath",
    "moveTo",
    "lineTo",
    "closePath",
    "clip",
    "transform",
    "setTransform",
    "drawImage",
  ];
  ctx = Object.fromEntries(
    methods.map((name) => [name, vi.fn()]),
  ) as unknown as CanvasRenderingContext2D;
  ctx.createLinearGradient = vi.fn(
    () => ({ addColorStop: vi.fn() }) as unknown as CanvasGradient,
  );
  vi.mocked(HTMLCanvasElement.prototype.getContext).mockReturnValue(ctx);
  vi.stubGlobal(
    "Image",
    class {
      naturalWidth = 960;
      naturalHeight = 960;
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) {
        queueMicrotask(() => this.onload?.());
      }
    },
  );
});

describe("computer renderer", () => {
  it("keeps a usable fallback when Canvas is unavailable", () => {
    vi.mocked(HTMLCanvasElement.prototype.getContext).mockReturnValue(null);
    const ready = vi.fn(),
      done = vi.fn();
    const computer = mountComputer(document.createElement("canvas"), ready);
    expect(computer.enter(done)).toBe(false);
    expect(ready).not.toHaveBeenCalled();
    computer.dispose();
  });

  it("loads the central layers, projects the image and completes exactly one zoom", async () => {
    const ready = vi.fn(),
      done = vi.fn(),
      duplicate = vi.fn();
    const computer = mountComputer(document.createElement("canvas"), ready);
    expect(computer.enter(done)).toBe(false);
    await loaded();
    tick(0);
    expect(ready).toHaveBeenCalledWith(true);
    expect(ctx.drawImage).toHaveBeenCalled();
    for (const args of vi.mocked(ctx.transform).mock.calls)
      expect(args.every(Number.isFinite)).toBe(true);
    expect(computer.enter(done)).toBe(true);
    expect(computer.enter(duplicate)).toBe(true);
    tick(ZOOM_DURATION - 1);
    expect(done).not.toHaveBeenCalled();
    tick(ZOOM_DURATION);
    expect(done).toHaveBeenCalledTimes(1);
    expect(duplicate).not.toHaveBeenCalled();
    computer.dispose();
  });

  it("cancels an active zoom without navigating", async () => {
    const computer = mountComputer(document.createElement("canvas"), vi.fn());
    await loaded();
    tick(0);
    const done = vi.fn();
    computer.enter(done);
    tick(200);
    computer.cancel();
    tick(ZOOM_DURATION);
    expect(done).not.toHaveBeenCalled();
    computer.dispose();
  });

  it("avoids zooming for reduced motion and never redirects on mount", async () => {
    vi.mocked(window.matchMedia).mockImplementation(
      (query) =>
        ({
          matches: query.includes("prefers-reduced-motion"),
          media: query,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
        }) as unknown as MediaQueryList,
    );
    const computer = mountComputer(document.createElement("canvas"), vi.fn());
    await loaded();
    tick(0);
    const done = vi.fn();
    expect(computer.enter(done)).toBe(false);
    expect(done).not.toHaveBeenCalled();
    computer.dispose();
  });

  it("does not switch angles on a touch device", async () => {
    vi.mocked(window.matchMedia).mockImplementation(
      (query) =>
        ({
          matches: query.includes("pointer: coarse"),
          media: query,
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
        }) as unknown as MediaQueryList,
    );
    const computer = mountComputer(document.createElement("canvas"), vi.fn());
    await loaded();
    tick(0);
    computer.point(0, 0);
    expect(callbacks.size).toBe(0);
    computer.dispose();
  });

  it("leaves the fallback available when an image fails", async () => {
    vi.stubGlobal(
      "Image",
      class {
        onload: (() => void) | null = null;
        onerror: (() => void) | null = null;
        set src(_value: string) {
          queueMicrotask(() => this.onerror?.());
        }
      },
    );
    const ready = vi.fn();
    const computer = mountComputer(document.createElement("canvas"), ready);
    await loaded();
    tick(0);
    await loaded();
    expect(ready).not.toHaveBeenCalled();
    expect(computer.enter(vi.fn())).toBe(false);
    computer.dispose();
  });

  it("does not navigate or update React after disposal", async () => {
    const ready = vi.fn();
    const computer = mountComputer(document.createElement("canvas"), ready);
    computer.dispose();
    await loaded();
    expect(ready).not.toHaveBeenCalled();
    expect(callbacks.size).toBe(0);
    expect(computer.enter(vi.fn())).toBe(false);
  });
});
