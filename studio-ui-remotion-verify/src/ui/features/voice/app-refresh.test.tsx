import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { App, fallback } from "../../App";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  delete window.newsflowDesktop;
});

it("shares a pending snapshot when the voice workspace is reopened", async () => {
  vi.useFakeTimers();
  const state = {
    ...fallback,
    scenarios: [{ index: 0, title: "Тема", state: "Готово", result: "Текст", error: "" }],
    voiceItems: [{ index: 0, title: "Тема", state: "Готово", path: "", voiceStatus: "WProject: создаёт озвучку" }],
  };
  let finish: ((value: NewsFlowSnapshot) => void) | undefined;
  const snapshot = vi.fn().mockResolvedValueOnce(state).mockImplementation(() => new Promise<NewsFlowSnapshot>((resolve) => { finish = resolve; }));
  Object.defineProperty(window, "newsflowDesktop", { configurable: true, value: { snapshot } });
  render(<App />);
  await act(async () => { await Promise.resolve(); });
  fireEvent.click(screen.getByRole("button", { name: "ПРОИЗВОДСТВО" }));
  fireEvent.click(screen.getByRole("button", { name: "Озвучка — очередь" }));
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  fireEvent.click(screen.getByRole("button", { name: "Центр управления" }));
  fireEvent.click(screen.getByRole("button", { name: "Озвучка — очередь" }));
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(snapshot).toHaveBeenCalledTimes(2); // startup + one outstanding read
  await act(async () => {
    finish?.({ ...state, voiceItems: [{ ...state.voiceItems[0], path: "D:/test/ready.mp3", voiceStatus: "Готово" }] });
  });
  expect(screen.getByText("ready.mp3")).toBeTruthy();
});
