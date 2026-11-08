import { useSyncExternalStore } from "react";

let context: AudioContext | undefined;
const windowId = crypto.randomUUID();
const listeners = new Set<() => void>();
const enabled = () => { try { return localStorage.getItem("rio.sound") !== "off"; } catch { return true; } };
export function setSoundEnabled(on: boolean) {
  try { localStorage.setItem("rio.sound", on ? "on" : "off"); } catch { /* Storage can be unavailable in a WebView. */ }
  listeners.forEach((notify) => notify());
}
window.addEventListener("storage", (event) => {
  if (event.key === "rio.sound" || event.key === null) listeners.forEach((notify) => notify());
  if (event.key === "rio.sound.request" && event.newValue && enabled()) {
    try {
      if (localStorage.getItem("rio.sound.owner") !== windowId) return;
      const { notes, duration, volume } = JSON.parse(event.newValue);
      if (Array.isArray(notes) && notes.length <= 3 && notes.every((note) => typeof note === "number" && note >= 100 && note <= 2000)
        && typeof duration === "number" && duration > 0 && duration <= 0.2 && typeof volume === "number" && volume >= 0 && volume <= 0.35) tone(notes, duration, volume, false);
    } catch { /* Ignore unavailable storage or malformed requests. */ }
  }
});
export function useSoundEnabled() {
  return useSyncExternalStore((notify) => { listeners.add(notify); return () => { listeners.delete(notify); }; }, enabled);
}
function unlock(event: Event) {
  if (!event.isTrusted || !enabled()) return;
  try {
    context ??= new AudioContext();
    try { localStorage.setItem("rio.sound.owner", windowId); } catch { /* Local playback still works. */ }
    if (context.state === "suspended") void context.resume().catch(() => {});
  } catch { /* Audio is optional. */ }
}
window.addEventListener("pointerdown", unlock, { capture: true });
window.addEventListener("keydown", unlock, { capture: true });

function tone(notes: number[], duration = 0.14, volume = 0.25, relay = true) {
  if (!enabled()) return;
  if (!context || context.state !== "running") {
    if (relay) {
      try { localStorage.setItem("rio.sound.request", JSON.stringify({ notes, duration, volume, id: crypto.randomUUID() })); } catch { /* No activated window is available. */ }
    }
    return;
  }
  const start = context.currentTime;
  notes.forEach((frequency, index) => {
    const at = start + index * duration * 0.6;
    const oscillator = context!.createOscillator();
    const gain = context!.createGain();
    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(frequency, at);
    gain.gain.setValueAtTime(0, at);
    gain.gain.linearRampToValueAtTime(0.15 * volume / notes.length, at + 0.008);
    gain.gain.exponentialRampToValueAtTime(0.0001, at + duration);
    oscillator.connect(gain);
    gain.connect(context!.destination);
    oscillator.start(at);
    oscillator.stop(at + duration);
    oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); };
  });
}

export const sfx = {
  tap: () => tone([420], 0.045, 0.1),
  open: () => tone([440, 660], 0.16),
  confirm: () => tone([540, 810], 0.12),
  step: () => tone([740], 0.075, 0.16),
  success: () => tone([523, 659, 784], 0.2, 0.35),
  error: () => tone([330, 220], 0.16, 0.3),
  micOn: () => tone([400, 600], 0.1),
  micOff: () => tone([600, 400], 0.1),
  hit: () => tone([580], 0.035, 0.16),
  dismiss: () => tone([380, 300], 0.1, 0.15),
};
