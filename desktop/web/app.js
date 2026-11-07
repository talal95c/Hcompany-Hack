/* The WebView renders native events only; no network or pedagogical policy. */
const $ = (id) => document.getElementById(id);
const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;
let pointerTimer, successTimer, currentStep;
const listeners = [];
const clear = () => { clearTimeout(pointerTimer); clearTimeout(successTimer); $("pointer").hidden = true; $("zone").hidden = true; $("success").hidden = true; };
const error = (value) => { $("error").textContent = String(value); $("dismiss-error").hidden = !value; };
const call = async (command, args) => { try { return await invoke(command, args); } catch (e) { error(e); return null; } };
const rendered = (p) => { if (p.command_id) requestAnimationFrame(() => requestAnimationFrame(() => call("render_ack", { commandId: p.command_id }))); };

if (location.hash !== "#pill") {
  listeners.push(listen("guide:clear", clear));
  listeners.push(listen("guide:pointer", ({ payload: p }) => {
    clear();
    $("pointer").style.left = `${p.x}px`; $("pointer").style.top = `${p.y}px`;
    for (const field of ["x", "y", "width", "height"]) {
      $("zone").style[{ x: "left", y: "top", width: "width", height: "height" }[field]] = `${p.zone[field]}px`;
    }
    $("pointer").hidden = false; $("zone").hidden = false;
    rendered(p);
    pointerTimer = setTimeout(clear, p.duration_ms);
  }));
  listeners.push(listen("guide:success", ({ payload: p }) => {
    clearTimeout(successTimer); clear();
    $("success-text").textContent = p.text; $("success").hidden = false;
    rendered(p);
    successTimer = setTimeout(clear, p.duration_ms);
  }));
} else {
  $("guide").hidden = true; $("pill").hidden = false;
  $("dismiss-error").onclick = () => error("");
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
  listeners.push(listen("sidecar:status", ({ payload }) => connection(payload === "connected")));
  listeners.push(listen("permission:changed", ({ payload }) => permissions(payload)));
  listeners.push(listen("native:error", ({ payload }) => error(payload)));
  listeners.push(listen("lesson:state", ({ payload }) => {
    if (payload.step_id !== currentStep || payload.status === "COMPLETE") $("instruction").textContent = payload.instruction;
    currentStep = payload.step_id;
  }));
  listeners.push(listen("speech:text", ({ payload }) => { $("instruction").textContent = payload; }));
  listeners.push(listen("audio:status", ({ payload }) => { $("mic").classList.toggle("active", payload); $("mic").textContent = payload ? "Je vous écoute…" : "Maintenir pour parler"; }));
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
Promise.all(listeners).then(() => invoke("frontend_ready")).catch(error);
