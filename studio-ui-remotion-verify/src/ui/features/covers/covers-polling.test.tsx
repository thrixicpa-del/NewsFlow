import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App, CoverGallery, Covers, fallback } from "../../App";

const state: NewsFlowSnapshot = {
  ...fallback,
  covers: Array.from({ length: 84 }, (_, index) => ({
    production_item_id: `production:${index + 1}`, scenario_index: index + 1,
    title: `Тема ${index + 1}`, status: "FastGen генерирует", paths: [],
    image_prompt: "Manual scene", prompt_provider: "manual",
  })),
};
const completed: NewsFlowSnapshot = {
  ...state,
  covers: state.covers.map((row, index) => index < 78
    ? { ...row, status: "Готово", progress: 100, paths: [`D:/fixture/cover-${index + 1}.png`] }
    : { ...row, status: index === 78 ? "Ожидает лимит FastGen" : "Требуется восстановление FastGen" }),
  coverCounts: { total: 84, ready: 78, missing: 6, failed: 0, queued: 1, generating: 0 },
};

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  delete window.newsflowDesktop;
  localStorage.clear();
});

describe("Covers durable refresh", () => {
  it("preserves Studio draft settings across an equivalent polling snapshot", () => {
    const view = render(<Covers data={state} command={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Настроить студию" }));
    const input = screen.getByLabelText(/Твой промпт для главных слов/);
    fireEvent.change(input, { target: { value: "Operator draft" } });
    view.rerender(<Covers data={{ ...state, coverSettings: structuredClone(state.coverSettings) }} command={vi.fn()} />);
    expect((input as HTMLTextAreaElement).value).toBe("Operator draft");
  });

  it("keeps a manual inspector bound to its ID after reorder and closes it after deletion", () => {
    const command = vi.fn();
    const data = { ...state, covers: [state.covers[0], state.covers[1]] };
    const view = render(<Covers data={data} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "1. Тема 1" }));
    const prompt = screen.getByPlaceholderText("Вставьте или отредактируйте ручной визуальный промпт");
    fireEvent.change(prompt, { target: { value: "Draft for first ID" } });
    view.rerender(<Covers data={{ ...data, covers: [...data.covers].reverse() }} command={command} />);
    expect((screen.getByPlaceholderText("Вставьте или отредактируйте ручной визуальный промпт") as HTMLTextAreaElement).value)
      .toBe("Draft for first ID");
    fireEvent.submit(screen.getByPlaceholderText("Вставьте или отредактируйте ручной визуальный промпт").closest("form")!);
    expect(command).toHaveBeenCalledWith("save-cover-manual-prompt", { productionItemId: "production:1", prompt: "Draft for first ID" });
    view.rerender(<Covers data={{ ...data, covers: [data.covers[1]] }} command={command} />);
    expect(screen.queryByPlaceholderText("Вставьте или отредактируйте ручной визуальный промпт")).toBeNull();
  });

  it("preserves the AI-reference draft across an equal background snapshot", () => {
    const command = vi.fn();
    const view = render(<Covers data={state} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Настроить студию" }));
    fireEvent.click(screen.getByText("Один набор для ИИ"));
    view.rerender(<Covers data={{ ...state, coverSettings: structuredClone(state.coverSettings) }} command={command} />);
    expect(screen.getByText("Один набор для ИИ").closest("button")?.className).toContain("selected");
    fireEvent.click(screen.getByRole("button", { name: "Сохранить для ИИ" }));
    expect(command).toHaveBeenCalledWith("save-cover-settings", expect.objectContaining({ aiReferenceMode: "all" }));
  });

  it("keeps selected Gallery variants tied to ID across reorder for a repeat action", () => {
    const command = vi.fn();
    const data = { ...completed, covers: [completed.covers[0], completed.covers[1]] };
    const view = render(<CoverGallery data={data} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "1. Тема 1" }));
    fireEvent.click(screen.getByTitle("Клик — увеличить; Ctrl+клик — выбрать несколько"), { ctrlKey: true });
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    view.rerender(<CoverGallery data={{ ...data, covers: [...data.covers].reverse() }} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Повторить текущие (1)" }));
    expect(command).toHaveBeenCalledWith("regenerate-covers", expect.objectContaining({
      indices: [1], productionItemIds: ["production:1"], currentProfile: true,
    }));
  });

  it("keeps Gallery face drafts on their ProductionItem across reorder", () => {
    const command = vi.fn();
    const data = { ...completed, covers: [completed.covers[0], completed.covers[1]] };
    const view = render(<CoverGallery data={data} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "1. Тема 1" }));
    const select = view.container.querySelector(".gallery-face-editor select") || document.querySelector(".gallery-face-editor select")!;
    fireEvent.change(select, { target: { value: "__none__" } });
    view.rerender(<CoverGallery data={{ ...data, covers: [...data.covers].reverse() }} command={command} />);
    expect((document.querySelector(".gallery-face-editor select") as HTMLSelectElement).value).toBe("__none__");
    view.rerender(<CoverGallery data={{ ...data, covers: [data.covers[1]] }} command={command} />);
    expect(document.querySelector(".gallery-face-editor select")).toBeNull();
  });
  it("updates Gallery while it is open without generating images", async () => {
    vi.useFakeTimers();
    const command = vi.fn();
    function Gallery() {
      const [data, setData] = useState(state);
      return <CoverGallery data={data} command={command} refresh={async () => { setData(completed); }} />;
    }
    render(<Gallery />);
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    const row = screen.getByRole("button", { name: "1. Тема 1" }).closest("tr")!;
    expect(within(row).getByText("1 готово")).toBeTruthy();
    expect(command).not.toHaveBeenCalled();
  });
  it("shows saved covers after reopening without another paid command", async () => {
    vi.useFakeTimers();
    const command = vi.fn();
    function Queue() {
      const [data, setData] = useState(state);
      return <Covers data={data} command={command} refresh={async () => { setData(completed); }} />;
    }
    const first = render(<Queue />);
    first.unmount();
    render(<Queue />);
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    const row = screen.getByRole("button", { name: "1. Тема 1" }).closest("tr")!;
    expect(within(row).getByText("Готово")).toBeTruthy();
    expect(within(row).getByText("1 картинок")).toBeTruthy();
    expect(command).not.toHaveBeenCalled();
  });

  it("serializes refreshes, retries failed reads and stops polling on unmount", async () => {
    vi.useFakeTimers();
    let finish: (() => void) | undefined;
    const refresh = vi.fn().mockRejectedValueOnce(new Error("access race"))
      .mockImplementation(() => new Promise<void>((resolve) => { finish = resolve; }));
    const view = render(<Covers data={state} command={vi.fn()} refresh={refresh} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(6000); });
    expect(refresh).toHaveBeenCalledTimes(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    expect(refresh).toHaveBeenCalledTimes(2);
    await act(async () => { finish?.(); });
    view.unmount();
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    expect(refresh).toHaveBeenCalledTimes(2);
  });

  it.each([
    { rateAutoResume: false, generationPaused: false },
    { rateAutoResume: true, generationPaused: true },
  ])("keeps disabled/paused quota resume from making a paid command during refresh: %o", async (flags) => {
    vi.useFakeTimers();
    const command = vi.fn();
    render(<Covers data={{ ...state, covers: [{ ...state.covers[0], status: "Ожидает лимит FastGen",
      rate_limit_wait_until: new Date(Date.now() - 60000).toISOString() }],
      coverSettings: { ...state.coverSettings, ...flags } }}
      command={command} refresh={vi.fn(async () => undefined)} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
    expect(command).not.toHaveBeenCalled();
  });

  it("fetches completed durable results after a batch rejects and retains its diagnostic", async () => {
    const snapshot = vi.fn().mockResolvedValueOnce(state).mockResolvedValue(completed);
    const command = vi.fn(async (name: string) => {
      if (name === "generate-covers") throw new Error("settings read failed after results were saved");
      return state;
    });
    Object.defineProperty(window, "newsflowDesktop", { configurable: true, value: { snapshot, command } });
    render(<App />);
    await act(async () => { await Promise.resolve(); });
    fireEvent.click(screen.getByRole("button", { name: "ОБЛОЖКИ И ГЕНЕРАЦИИ" }));
    fireEvent.click(screen.getByRole("button", { name: "Обложки YouTube" }));
    fireEvent.click(screen.getByRole("button", { name: "Создать обложки" }));
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    const row = screen.getByRole("button", { name: "1. Тема 1" }).closest("tr")!;
    expect(within(row).getByText("Готово")).toBeTruthy();
    expect(screen.getByText(/Не выполнено:.*settings read failed/)).toBeTruthy();
    expect(command.mock.calls.filter(([name]) => name === "generate-covers")).toHaveLength(1);
  });
});
