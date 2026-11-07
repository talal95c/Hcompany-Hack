import { readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import geometry from "../public/computer/frames.json";

describe("original computer assets", () => {
  it("ships all 57 WebP views and valid projected screen coordinates", () => {
    expect(geometry.frames).toHaveLength(geometry.rows * geometry.columns);
    let total = 0;
    for (const frame of geometry.frames) {
      const path = resolve(
        "public/computer",
        `frame-${frame.row}-${frame.column}.webp`,
      );
      const bytes = readFileSync(path);
      expect(bytes.subarray(0, 4).toString()).toBe("RIFF");
      expect(bytes.subarray(8, 12).toString()).toBe("WEBP");
      total += statSync(path).size;
      for (const corner of frame.screen) {
        expect(corner).toHaveLength(2);
        for (const coordinate of corner) {
          expect(coordinate).toBeGreaterThan(0);
          expect(coordinate).toBeLessThan(1);
        }
      }
    }
    expect(total).toBeLessThan(1_000_000);
  });
});
