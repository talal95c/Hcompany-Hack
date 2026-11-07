/* The WebView renders native events only; no network or pedagogical policy. */
const $ = (id) => document.getElementById(id);
const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;
let pointerTimer, successTimer;
const clear = () => { $("pointer").hidden = true; $("zone").hidden = true; $("success").hidden = true; };
const error = (value) => { $("error").textContent = String(value); };
const call = async (command, args) => { try { $("error").textContent = ""; return await invoke(command, args); } catch (e) { error(e); return null; } };

if (location.hash !== "#pill") {
  listen("guide.clear", clear);
  listen("guide.pointer", ({ payload: p }) => {
    clearTimeout(pointerTimer);
    $("pointer").style.left = `${p.x}px`; $("pointer").style.top = `${p.y}px`;
    for (const field of ["x", "y", "width", "height"]) {
      $("zone").style[{ x: "left", y: "top", width: "width", height: "height" }[field]] = `${p.zone[field]}px`;
    }
    $("pointer").hidden = false; $("zone").hidden = false;
    pointerTimer = setTimeout(clear, p.duration_ms);
  });
  listen("guide.success", ({ payload: p }) => {
    clearTimeout(successTimer); clear();
    $("success-text").textContent = p.text; $("success").hidden = false;
    successTimer = setTimeout(clear, p.duration_ms);
  });
} else {
  $("guide").hidden = true; $("pill").hidden = false;
  let expanded = false;
  $("expand").onclick = async () => {
    expanded = !expanded;
    await call("panel_toggle", { expanded });
    $("panel").hidden = !expanded;
    $("expand").setAttribute("aria-expanded", String(expanded));
  };
  const permissions = (p) => {
    $("permissions").replaceChildren();
    for (const [key, label] of [["screen", "Écran"], ["accessibility", "Contrôle"], ["microphone", "Micro"]]) {
      const button = document.createElement("button");
      button.textContent = `${p[key] ? "✓" : "!"} ${label}`;
      button.onclick = async () => { const next = await call("permission_request", { kind: key }); if (next) permissions(next); };
      $("permissions").append(button);
    }
  };
  const connection = (connected) => {
    $("connection").classList.toggle("online", connected);
    $("status").textContent = connected ? "Connecté" : "Déconnecté";
    if (!connected) { $("consent").checked = false; $("delegate").disabled = true; }
  };
  const refresh = async () => {
    try {
      const p = await invoke("desktop_status"); connection(p.connected); permissions(p.permissions);
      $("shortcuts").textContent = `Voix : ${p.ptt_hotkey} · Arrêt prioritaire : ${p.stop_hotkey}`;
    } catch (e) { error(e); }
  };
  listen("sidecar.status", ({ payload }) => connection(payload === "connected"));
  listen("permission.changed", ({ payload }) => permissions(payload));
  listen("native.error", ({ payload }) => error(payload));
  listen("lesson.state", ({ payload }) => { $("instruction").textContent = payload.instruction; });
  listen("speech.text", ({ payload }) => { $("instruction").textContent = payload; });
  listen("audio.status", ({ payload }) => { $("mic").classList.toggle("active", payload); $("mic").textContent = payload ? "Je vous écoute…" : "Maintenir pour parler"; });
  $("mic").onpointerdown = (event) => { event.currentTarget.setPointerCapture(event.pointerId); call("ptt", { active: true }); };
  $("mic").onpointerup = $("mic").onpointercancel = () => call("ptt", { active: false });
  window.addEventListener("blur", () => call("ptt", { active: false }));
  $("stop").onclick = () => { $("consent").checked = false; $("delegate").disabled = true; call("stop_actions"); };
  $("consent").onchange = () => { $("delegate").disabled = !$("consent").checked; };
  $("delegate").onclick = async () => { await call("consent_grant"); $("consent").checked = false; $("delegate").disabled = true; };
  $("capture").onsubmit = async (event) => {
    event.preventDefault(); const crop = {};
    for (const [key, value] of new FormData(event.currentTarget)) crop[key] = Number(value);
    await call("capture_region", { crop });
  };
  $("question").onsubmit = async (event) => { event.preventDefault(); if (await call("user_intent", { text: $("text").value }) !== null) $("text").value = ""; };
  $("restart").onclick = async () => { await call("sidecar_stop"); setTimeout(() => call("sidecar_start"), 500); };
  $("quit").onclick = () => call("quit");
  refresh(); setInterval(refresh, 3000);
}
