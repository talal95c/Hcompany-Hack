import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App, { DESTINATION } from "../src/App";
import { mountComputer } from "../src/computer";

const renderer = vi.hoisted(() => ({
  point: vi.fn(),
  reset: vi.fn(),
  hover: vi.fn(),
  enter: vi.fn(),
  cancel: vi.fn(),
  dispose: vi.fn(),
}));
vi.mock("../src/computer", () => ({ mountComputer: vi.fn(() => renderer) }));

beforeEach(() => {
  vi.clearAllMocks();
  renderer.enter.mockReturnValue(true);
});

describe("computer only", () => {
  it("shows just the computer, with a real Google link and no marketing", () => {
    render(<App />);
    expect(screen.getByRole("link")).toHaveAttribute("href", DESTINATION);
    expect(screen.getByRole("link")).toHaveAccessibleName(
      "Cliquer sur l’ordinateur pour ouvrir Google",
    );
    expect(screen.queryByRole("navigation")).toBeNull();
    expect(screen.queryByRole("heading")).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("does not bypass the computer because of the previous intro storage or a hash", () => {
    sessionStorage.setItem("holo-tutor:intro-seen", "true");
    history.replaceState({}, "", "/#accueil");
    render(<App />);
    expect(screen.getByRole("link")).toBeVisible();
  });

  it("starts one zoom and blocks repeated activation", () => {
    const view = render(<App />);
    const link = screen.getByRole("link");
    fireEvent.click(link);
    fireEvent.click(link);
    expect(renderer.enter).toHaveBeenCalledTimes(1);
    expect(renderer.enter).toHaveBeenCalledWith(expect.any(Function));
    expect(link).toHaveAttribute("aria-busy", "true");
    expect(view.container.firstChild).toHaveClass("crt--zooming");
  });

  it("supports focus, Space and Escape without an extra intro button", async () => {
    render(<App />);
    const link = screen.getByRole("link");
    await userEvent.tab();
    expect(link).toHaveFocus();
    expect(renderer.hover).toHaveBeenCalledWith(true);
    fireEvent.keyDown(link, { key: " " });
    expect(renderer.enter).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(link, { key: "Escape" });
    expect(renderer.cancel).toHaveBeenCalledTimes(1);
    expect(link).toHaveAttribute("aria-busy", "false");
  });

  it("keeps the image/link fallback until the renderer is ready", () => {
    const { container } = render(<App />);
    expect(container.querySelector("img")).toHaveAttribute(
      "src",
      "/crt/poster.png",
    );
    const ready = vi.mocked(mountComputer).mock.calls[0][1];
    act(() => ready(true));
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      "https://www.google.com/",
    );
  });

  it("preserves modified link clicks", () => {
    render(<App />);
    const link = screen.getByRole("link");
    link.addEventListener("click", (event) => event.preventDefault());
    fireEvent.click(link, { ctrlKey: true });
    fireEvent.click(link, { metaKey: true });
    expect(renderer.enter).not.toHaveBeenCalled();
  });

  it("restores a usable computer after returning from Google via browser back", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("link"));
    act(() =>
      window.dispatchEvent(
        new PageTransitionEvent("pageshow", { persisted: true }),
      ),
    );
    expect(renderer.cancel).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("link")).toHaveAttribute("aria-busy", "false");
  });

  it("disposes resources and listeners when unmounted", () => {
    const view = render(<App />);
    view.unmount();
    expect(renderer.dispose).toHaveBeenCalledTimes(1);
    window.dispatchEvent(new Event("pointermove"));
    expect(renderer.point).not.toHaveBeenCalled();
  });
});
