import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "../src/App";
import { INTRO_KEY, shouldShowIntro } from "../src/intro";

function visitLanding() {
  sessionStorage.setItem(INTRO_KEY, "true");
  return render(<App />);
}

describe("entrance", () => {
  it("hands off the animated screen zoom to the live page and cancels resources", async () => {
    vi.stubGlobal(
      "Image",
      class {
        onload: (() => void) | null = null;
        onerror: (() => void) | null = null;
        set src(_value: string) {
          queueMicrotask(() => this.onload?.());
        }
      },
    );
    vi.mocked(HTMLCanvasElement.prototype.getContext).mockReturnValue({
      clearRect: vi.fn(),
      drawImage: vi.fn(),
    } as unknown as CanvasRenderingContext2D);
    const { container } = render(<App />);
    await waitFor(() =>
      expect(container.querySelector(".computer-fallback")).toBeNull(),
    );
    const button = screen.getByRole("button", {
      name: "Entrer dans Holo Tutor",
    });
    const cancel = vi.fn();
    const animate = vi.fn<
      (
        keyframes: Keyframe[],
        options: KeyframeAnimationOptions,
      ) => { cancel: typeof cancel }
    >(() => ({ cancel }));
    Object.assign(button, { animate });
    Object.assign(screen.getByRole("dialog"), { animate });
    vi.spyOn(button, "getBoundingClientRect").mockReturnValue({
      left: 200,
      top: 100,
      width: 500,
      height: 500,
    } as DOMRect);
    vi.useFakeTimers();
    fireEvent.click(button);
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(animate).toHaveBeenCalledTimes(2);
    expect(animate.mock.calls[0][0][1].transform).not.toMatch(/Infinity|NaN/);
    act(() => {
      vi.advanceTimersByTime(1150);
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(sessionStorage.getItem(INTRO_KEY)).toBe("true");
    expect(cancel).toHaveBeenCalledTimes(2);
  });

  it("starts with an accessible entrance and keeps the live page inert", async () => {
    const { container } = render(<App />);
    expect(screen.getByRole("dialog")).toHaveAccessibleName(
      "Le prochain clic, c’est le vôtre.",
    );
    expect(container.querySelector(".site")).toHaveAttribute("inert");
    expect(document.body.style.overflow).toBe("hidden");
    expect(screen.getByRole("dialog")).toHaveFocus();
    await userEvent.tab();
    expect(
      screen.getByRole("button", { name: "Entrer dans Holo Tutor" }),
    ).toHaveFocus();
    await userEvent.tab();
    expect(
      screen.getByRole("button", { name: "Passer l’intro" }),
    ).toHaveFocus();
    await userEvent.tab({ shift: true });
    expect(
      screen.getByRole("button", { name: "Entrer dans Holo Tutor" }),
    ).toHaveFocus();
  });

  it("skips, remembers the entrance, restores scrolling and does not repeat on remount", async () => {
    const view = render(<App />);
    await userEvent.click(
      screen.getByRole("button", { name: "Passer l’intro" }),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(sessionStorage.getItem(INTRO_KEY)).toBe("true");
    expect(document.body.style.overflow).toBe("");
    expect(view.container.querySelector(".site")).not.toHaveAttribute("inert");
    view.unmount();
    render(<App />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("accepts Escape and keyboard activation without WebGL or the animation API", async () => {
    render(<App />);
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Rejouer l’intro" }),
    );
    await userEvent.keyboard("{Enter}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("does not block the page when the computer image fails", async () => {
    const { container } = render(<App />);
    fireEvent.error(container.querySelector(".computer-fallback")!);
    expect(screen.getByText(/Le décor n’a pas chargé/)).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Entrer dans Holo Tutor" }),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("bypasses the entrance for reduced motion and direct section links", () => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    vi.mocked(window.matchMedia).mockReturnValue({ ...media, matches: true });
    expect(shouldShowIntro()).toBe(false);
    render(<App />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    vi.mocked(window.matchMedia).mockReturnValue({ ...media, matches: false });
    history.replaceState({}, "", "/#questions");
    expect(shouldShowIntro()).toBe(false);
  });

  it("works even if session storage is unavailable", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    render(<App />);
    await userEvent.click(
      screen.getByRole("button", { name: "Passer l’intro" }),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("landing", () => {
  it("links every local anchor to an existing section, and installation to the real project", () => {
    const { container } = visitLanding();
    for (const anchor of container.querySelectorAll<HTMLAnchorElement>(
      'a[href^="#"]',
    )) {
      expect(document.getElementById(anchor.hash.slice(1))).not.toBeNull();
    }
    const installs = screen.getAllByRole("link", { name: /Installer/ });
    expect(installs).toHaveLength(3);
    for (const link of installs)
      expect(link).toHaveAttribute(
        "href",
        "https://github.com/talal95c/Hcompany-Hack/tree/main/h-tutor#run",
      );
    expect(
      screen.queryByRole("button", { name: /Télécharger/ }),
    ).not.toBeInTheDocument();
    expect(container.querySelector("form")).toBeNull();
  });

  it("updates the illustrated preview and opens the corresponding explanation", async () => {
    visitLanding();
    const selector = screen.getByRole("group", {
      name: "Explorer l’aperçu du guide",
    });
    const second = within(selector).getByRole("button", {
      name: /Une indication à l’écran/,
    });
    await userEvent.click(second);
    expect(second).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByText("Ouvrez le menu « Ajouter » dans la vue 3D."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Repérez le prochain geste/ }),
    ).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(
      screen.getByRole("button", { name: /Faites-le vous-même/ }),
    );
    expect(
      screen.getByText("Une question ? Demandez à Holo de réexpliquer."),
    ).toBeInTheDocument();
    expect(screen.getByText(/Pas une session en direct/)).toBeInTheDocument();
  });

  it("opens and closes mobile navigation, including Escape", async () => {
    visitLanding();
    const toggle = screen.getByRole("button", { name: "Ouvrir le menu" });
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(document.body.style.overflow).toBe("hidden");
    await userEvent.click(
      within(screen.getByRole("navigation")).getByRole("link", {
        name: "Questions",
      }),
    );
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(document.body.style.overflow).toBe("");
    await userEvent.click(toggle);
    within(screen.getByRole("navigation"))
      .getByRole("link", { name: "Questions" })
      .focus();
    await userEvent.keyboard("{Escape}");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveFocus();
  });

  it("exposes native FAQ disclosures and honest platform/privacy limitations", () => {
    const { container } = visitLanding();
    expect(container.querySelectorAll("details")).toHaveLength(5);
    expect(
      screen.getByText(/Il n’y a pas encore d’installateur publié/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/consultez leur politique de rétention/),
    ).toBeInTheDocument();
  });
});
