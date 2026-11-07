import { describe, expect, it } from "vitest";
import {
  bounds,
  initialRect,
  screenMesh,
  smoothstep,
  zoomProgress,
  zoomRect,
} from "../src/crtGeometry";

describe("screen geometry", () => {
  it("projects every view to finite coordinates inside the rendered frame", () => {
    for (let y = 0; y < 3; y++)
      for (let x = 0; x < 19; x++) {
        for (const point of screenMesh(x, y)) {
          expect(point.x).toBeGreaterThan(0);
          expect(point.x).toBeLessThan(1);
          expect(point.y).toBeGreaterThan(0);
          expect(point.y).toBeLessThan(1);
        }
      }
  });

  it.each([
    [1440, 900],
    [390, 844],
    [320, 568],
    [844, 390],
  ])(
    "keeps the small computer centred and zooms through the screen at %sx%s",
    (width, height) => {
      const from = initialRect(width, height);
      expect(from.x + from.size / 2).toBeCloseTo(width / 2);
      expect(from.size).toBeLessThan(width);
      for (const [column, row] of [
        [0, 0],
        [9, 1],
        [18, 2],
      ]) {
        const mesh = screenMesh(column, row),
          box = bounds(mesh);
        const to = zoomRect(mesh, width, height);
        expect(to.size).toBeGreaterThan(from.size);
        expect(to.x + box.x * to.size).toBeLessThan(0);
        expect(to.y + box.y * to.size).toBeLessThan(0);
        expect(to.x + (box.x + box.width) * to.size).toBeGreaterThan(width);
        expect(to.y + (box.y + box.height) * to.size).toBeGreaterThan(height);
      }
    },
  );

  it("has bounded, monotonic zoom and flattening progress", () => {
    let previous = 0;
    for (let n = 0; n <= 100; n++) {
      const value = zoomProgress(n / 100);
      expect(value).toBeGreaterThanOrEqual(previous);
      expect(value).toBeLessThanOrEqual(1);
      previous = value;
    }
    expect(zoomProgress(0)).toBe(0);
    expect(zoomProgress(1)).toBe(1);
    expect(smoothstep(0.1, 0.48, 0)).toBe(0);
    expect(smoothstep(0.1, 0.48, 1)).toBe(1);
  });
});
