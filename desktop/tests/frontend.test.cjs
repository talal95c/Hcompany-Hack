const { test } = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { runInNewContext } = require("node:vm");
const source = readFileSync(`${__dirname}/../web/app.js`, "utf8");
const flush = () => new Promise(setImmediate);

function frontend(hash) {
  const elements = new Map(), listeners = new Map(), calls = [], timers = new Map();
  let timerId = 0;
  const element = () => ({
    textContent: "", hidden: true, style: {},
    classList: { toggle() {} }, replaceChildren() {}, setAttribute() {}, append() {},
  });
  const get = (id) => {
    if (!elements.has(id)) elements.set(id, element());
    return elements.get(id);
  };
  runInNewContext(source, {
    document: { getElementById: get, createElement: element }, location: { hash },
    window: { addEventListener() {}, __TAURI__: {
      core: { invoke: async (name) => {
        calls.push(name);
        return name === "desktop_status" ? { connected: true, permissions: {} } : undefined;
      } },
      event: { listen: (name, callback) => new Promise((resolve, reject) => {
        listeners.set(name, { callback, resolve, reject });
      }) },
    } },
    setInterval() {},
    setTimeout(callback) { const id = ++timerId; timers.set(id, callback); return id; },
    clearTimeout(id) { timers.delete(id); },
  });
  return { get, listeners, calls, timers };
}

for (const hash of ["#guide", "#pill"]) {
  test(`${hash} acknowledges readiness only after every listener`, async () => {
    const ui = frontend(hash);
    const registrations = [...ui.listeners.values()];
    registrations.slice(1).forEach(({ resolve }) => resolve(() => {}));
    await flush();
    assert.ok(!ui.calls.includes("frontend_ready"));
    registrations[0].resolve(() => {});
    await flush();
    assert.equal(ui.calls.filter((name) => name === "frontend_ready").length, 1);
  });
}

test("listener failure stays visible and cannot start the engine", async () => {
  const ui = frontend("#pill");
  ui.listeners.get("native:error").reject(new Error("listener unavailable"));
  await flush();
  assert.ok(!ui.calls.includes("frontend_ready"));
  assert.match(ui.get("error").textContent, /listener unavailable/);
});

test("expanding and status refresh preserve native errors until explicit dismissal", async () => {
  const ui = frontend("#pill");
  ui.listeners.get("native:error").callback({ payload: "Native failure" });
  await ui.get("expand").onclick();
  await flush();
  assert.equal(ui.get("error").textContent, "Native failure");
  assert.equal(ui.get("dismiss-error").hidden, false);
  ui.get("dismiss-error").onclick();
  assert.equal(ui.get("error").textContent, "");
  assert.equal(ui.get("dismiss-error").hidden, true);
});

test("new guide events and stop cancel old expiry timers", () => {
  const ui = frontend("#guide");
  const pointer = () => ui.listeners.get("guide:pointer").callback({ payload: {
    x: 10, y: 20, zone: { x: 0, y: 0, width: 100, height: 50 }, duration_ms: 5000,
  } });
  pointer();
  assert.equal(ui.get("pointer").hidden, false);
  assert.equal(ui.timers.size, 1);
  ui.listeners.get("guide:success").callback({ payload: { text: "Verified", duration_ms: 2500 } });
  assert.equal(ui.get("pointer").hidden, true);
  assert.equal(ui.get("success").hidden, false);
  assert.equal(ui.timers.size, 1);
  pointer();
  assert.equal(ui.get("success").hidden, true);
  assert.equal(ui.timers.size, 1);
  ui.listeners.get("guide:clear").callback();
  assert.equal(ui.get("pointer").hidden, true);
  assert.equal(ui.get("zone").hidden, true);
  assert.equal(ui.timers.size, 0);
});
