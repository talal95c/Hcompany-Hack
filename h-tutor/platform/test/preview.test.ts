import assert from "node:assert/strict";
import { test } from "node:test";
import { previewFromHtml } from "../src/ingest.ts";

const page = "https://blog.example.com/posts/bevel";

test("a page's og:image and site name, whatever the attribute order", () => {
  const html = `<head><meta content="https://cdn.example.com/cover.png" property="og:image">
    <meta property="og:site_name" content="Example &amp; Co"></head>`;
  assert.deepEqual(previewFromHtml(html, page), { image: "https://cdn.example.com/cover.png", site: "Example & Co" });
});

test("a relative image is made absolute; twitter:image when there is no og:image", () => {
  assert.deepEqual(previewFromHtml(`<meta name="twitter:image" content='/img/a.jpg'>`, page), { image: "https://blog.example.com/img/a.jpg" });
});

test("og:image wins over twitter:image, the secure URL over both", () => {
  const html = `<meta name="twitter:image" content="https://x.example/t.png"><meta property="og:image" content="https://x.example/o.png">
    <meta property="og:image:secure_url" content="https://x.example/s.png">`;
  assert.equal(previewFromHtml(html, page).image, "https://x.example/s.png");
});

test("an http image is dropped: the https console would block it", () => {
  assert.deepEqual(previewFromHtml(`<meta property="og:image" content="http://x.example/o.png">`, page), {});
});

test("no preview: nothing", () => {
  assert.deepEqual(previewFromHtml("<head><title>t</title></head>", page), {});
  assert.deepEqual(previewFromHtml(`<meta property="og:image" content="">`, page), {});
});
