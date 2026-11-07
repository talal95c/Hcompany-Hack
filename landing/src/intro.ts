export const INTRO_KEY = "holo-tutor:intro-seen";

export function shouldShowIntro(): boolean {
  if (
    window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
    window.location.hash
  )
    return false;
  try {
    return sessionStorage.getItem(INTRO_KEY) !== "true";
  } catch {
    return true;
  }
}

export function rememberIntro(): void {
  try {
    sessionStorage.setItem(INTRO_KEY, "true");
  } catch {
    // Private browsing can disable storage; navigation must still work.
  }
}
