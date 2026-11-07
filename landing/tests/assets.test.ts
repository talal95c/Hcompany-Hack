import { readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import sources from "../public/crt/sources.json";

describe("CRT assets", () => {
  it("ships both layers of all 57 angles locally, with provenance", () => {
    expect(Object.keys(sources.assets)).toHaveLength(114);
    let total = 0;
    for (let row = 0; row < 3; row++)
      for (let column = 0; column < 19; column++) {
        for (const layer of ["case", "glass"]) {
          const name = `${layer}-${row}-${column}.webp`;
          const path = resolve("public/crt", name);
          const bytes = readFileSync(path);
          expect(bytes.subarray(0, 4).toString()).toBe("RIFF");
          expect(bytes.subarray(8, 12).toString()).toBe("WEBP");
          expect(sources.assets).toHaveProperty(
            name,
            expect.stringMatching(/^https:\/\/cyze.dev\//),
          );
          total += statSync(path).size;
        }
      }
    expect(total).toBeLessThan(3_500_000);
  });

  it("ships the fallback poster and a no-JavaScript link", () => {
    expect(
      readFileSync("public/crt/poster.png").subarray(1, 4).toString(),
    ).toBe("PNG");
    const html = readFileSync("index.html", "utf8");
    expect(html).toMatch(/<noscript\s*>/);
    expect(html).toContain('href="https://www.google.com/"');
  });
});
