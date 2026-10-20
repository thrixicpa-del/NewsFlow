import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BrowserTopicScenarios, fallback } from "../../App";

describe("browser topic scenarios", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the current TXT export failure while protecting the completed text and preserving historical manual results", () => {
    const exportError = "ChatGPT вернул сценарий, но TXT не удалось сохранить: диск недоступен";
    const data = { ...fallback, scenarios: [{
      index: 0, productionItemId: "export-failure", title: "Export failure", state: "Ошибка",
      result: "Completed browser text retained in the queue", error: exportError,
    }, {
      index: 1, productionItemId: "manual-result", title: "Manual result", state: "Ошибка",
      result: "Historical manually saved text", error: "Старый технический статус",
    }] };
    const command = vi.fn(async () => data);
    render(<BrowserTopicScenarios data={data} command={command} />);
    const failedRow = screen.getByText("Export failure").closest("tr")!;
    expect(within(failedRow).getByText(`Ошибка: ${exportError}`)).toBeTruthy();
    expect(within(failedRow).queryByText("Готово")).toBeNull();
    expect((screen.getByLabelText("Выбрать: Export failure") as HTMLInputElement).disabled).toBe(true);
    const manualRow = screen.getByText("Manual result").closest("tr")!;
    expect(within(manualRow).getByText("Готово")).toBeTruthy();
    expect(within(manualRow).queryByText(/Старый технический статус/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Выбрать все новые темы" }));
    expect((screen.getByRole("button", { name: "Создать сценарии в ChatGPT" }) as HTMLButtonElement).disabled).toBe(true);
    expect(command).not.toHaveBeenCalled();
  });

  it("adds all selected requirement files without a count cap and removes only the requested file", async () => {
    const files = Array.from({ length: 24 }, (_, index) => `C:/disposable/requirements-${index}.txt`);
    const choose = vi.fn().mockResolvedValueOnce(files).mockResolvedValueOnce([files[0], "C:/disposable/style.md"]);
    vi.stubGlobal("newsflowDesktop", { chooseBrowserScenarioRequirementsFiles: choose });
    const data = { ...fallback, browserTopicScenarios: { ...fallback.browserTopicScenarios, requirementsMode: "file" as const } };
    const command = vi.fn(async () => data);
    render(<BrowserTopicScenarios data={data} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Добавить файлы" }));
    await waitFor(() => expect(screen.getByDisplayValue(files[23])).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Добавить файлы" }));
    await waitFor(() => expect(screen.getByDisplayValue("C:/disposable/style.md")).toBeTruthy());
    expect(screen.getAllByDisplayValue(files[0])).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: `Удалить файл: ${files[0]}` }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить настройки" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-browser-topic-scenario-settings", expect.objectContaining({
      requirementsFiles: [...files.slice(1), "C:/disposable/style.md"], requirementsFile: files[1],
    })));
  });

  it("loads the legacy single path and allows clearing it without reviving the fallback", async () => {
    const data = { ...fallback, browserTopicScenarios: { ...fallback.browserTopicScenarios,
      requirementsMode: "file" as const, requirementsFiles: undefined, requirementsFile: "C:/disposable/legacy.md" } };
    const command = vi.fn(async () => data);
    render(<BrowserTopicScenarios data={data} command={command} />);
    expect(screen.getByDisplayValue("C:/disposable/legacy.md")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Удалить файл: C:/disposable/legacy.md" }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить настройки" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-browser-topic-scenario-settings", expect.objectContaining({
      requirementsFiles: [], requirementsFile: "",
    })));
  });

  it("keeps selected files when the native chooser is cancelled", async () => {
    vi.stubGlobal("newsflowDesktop", { chooseBrowserScenarioRequirementsFiles: vi.fn().mockResolvedValue([]) });
    const data = { ...fallback, browserTopicScenarios: { ...fallback.browserTopicScenarios,
      requirementsMode: "file" as const, requirementsFiles: ["C:/disposable/retained.txt"] } };
    render(<BrowserTopicScenarios data={data} command={vi.fn(async () => data)} />);
    fireEvent.click(screen.getByRole("button", { name: "Добавить файлы" }));
    await waitFor(() => expect(screen.getByDisplayValue("C:/disposable/retained.txt")).toBeTruthy());
  });

  it("can cancel a restored active queue without selecting a topic and shows attachment progress", async () => {
    const data = { ...fallback, browserTopicScenarios: { ...fallback.browserTopicScenarios, running: true }, scenarios: [{
      index: 0, productionItemId: "pending", title: "Pending", state: "В работе", result: "",
      error: "Ожидается готовность вложений. Можно прикрепить файлы вручную.",
    }] };
    const command = vi.fn(async () => data);
    render(<BrowserTopicScenarios data={data} command={command} />);
    expect(screen.getByText(data.scenarios[0].error)).toBeTruthy();
    const cancel = screen.getByRole("button", { name: "Отменить генерацию" }) as HTMLButtonElement;
    expect(cancel.disabled).toBe(false);
    fireEvent.click(cancel);
    await waitFor(() => expect(command).toHaveBeenCalledWith("cancel-browser-topic-scenarios", {}));
  });

  it("does not reset draft settings when only the running snapshot changes", () => {
    const data = { ...fallback };
    const command = vi.fn(async () => data);
    const { rerender } = render(<BrowserTopicScenarios data={data} command={command} />);
    fireEvent.change(screen.getByLabelText("Сопроводительное письмо"), { target: { value: "Unsaved draft" } });
    rerender(<BrowserTopicScenarios data={{ ...data, browserTopicScenarios: { ...data.browserTopicScenarios, running: true } }} command={command} />);
    expect((screen.getByLabelText("Сопроводительное письмо") as HTMLTextAreaElement).value).toBe("Unsaved draft");
  });

  it("does not dispatch generation if cancellation occurs while launch settings are saving", async () => {
    const data = { ...fallback, scenarios: [{ index: 0, productionItemId: "pending-save", title: "Pending save", state: "Ожидает", result: "", error: "" }] };
    let release!: () => void;
    const saving = new Promise<void>((resolve) => { release = resolve; });
    const command = vi.fn(async (name: string) => {
      if (name === "save-browser-topic-scenario-settings") await saving;
      return data;
    });
    render(<BrowserTopicScenarios data={data} command={command} />);
    fireEvent.click(screen.getByLabelText("Выбрать: Pending save"));
    fireEvent.click(screen.getByRole("button", { name: "Создать сценарии в ChatGPT" }));
    fireEvent.click(screen.getByRole("button", { name: "Отменить генерацию" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("cancel-browser-topic-scenarios", { batchId: expect.any(String) }));
    await act(async () => { release(); });
    expect(command.mock.calls.filter(([name]) => name === "generate-browser-topic-scenarios")).toHaveLength(0);
  });

  it("cancels the same launch ID after generation dispatch before Core has claimed its queue", async () => {
    const data = { ...fallback, scenarios: [{ index: 0, productionItemId: "startup-race", title: "Startup race", state: "Ожидает", result: "", error: "" }] };
    let release!: () => void;
    const pending = new Promise<void>((resolve) => { release = resolve; });
    const command = vi.fn(async (name: string, _payload?: Record<string, unknown>) => {
      if (name === "generate-browser-topic-scenarios") await pending;
      return data;
    });
    render(<BrowserTopicScenarios data={data} command={command} />);
    fireEvent.click(screen.getByLabelText("Выбрать: Startup race"));
    fireEvent.click(screen.getByRole("button", { name: "Создать сценарии в ChatGPT" }));
    try {
      await waitFor(() => expect(command.mock.calls.some(([name]) => name === "generate-browser-topic-scenarios")).toBe(true));
      const generation = command.mock.calls.find(([name]) => name === "generate-browser-topic-scenarios")![1];
      expect(generation?.batchId).toEqual(expect.stringMatching(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i));
      fireEvent.click(screen.getByRole("button", { name: "Отменить генерацию" }));
      await waitFor(() => expect(command).toHaveBeenCalledWith("cancel-browser-topic-scenarios", { batchId: generation!.batchId }));
    } finally {
      await act(async () => { release(); });
    }
  });
  it("refreshes completed topics while another tab is pending without resetting draft settings", async () => {
    vi.useFakeTimers();
    let release!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    const data = { ...fallback, scenarios: [
      { index: 0, productionItemId: "fast", title: "Fast topic", state: "Ожидает", result: "", error: "" },
      { index: 1, productionItemId: "slow", title: "Slow topic", state: "Ожидает", result: "", error: "" },
    ] };
    const command = vi.fn(async (name: string) => {
      if (name === "generate-browser-topic-scenarios") await gate;
      return data;
    });
    const refreshed = { ...data, browserTopicScenarios: { ...data.browserTopicScenarios },
      scenarios: [{ ...data.scenarios[0], state: "Готово", result: "Downloaded TXT" },
        { ...data.scenarios[1], state: "В обработке" }] };
    let update!: () => void;
    const refresh = vi.fn(async () => { update(); });
    const { rerender, unmount } = render(<BrowserTopicScenarios data={data} command={command} refresh={refresh} />);
    update = () => rerender(<BrowserTopicScenarios data={refreshed} command={command} refresh={refresh} />);
    try {
      fireEvent.click(screen.getByLabelText("Выбрать: Fast topic"));
      await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Создать сценарии в ChatGPT" })); });
      expect(command).toHaveBeenCalledWith("generate-browser-topic-scenarios", {
        indices: [0], productionItemIds: ["fast"], batchId: expect.any(String),
      });
      fireEvent.change(screen.getByLabelText("Сопроводительное письмо"), { target: { value: "Unsaved draft" } });
      await act(async () => { await vi.advanceTimersByTimeAsync(1200); });
      expect(refresh).toHaveBeenCalled();
      expect(screen.getByText("Готово")).toBeTruthy();
      expect((screen.getByLabelText("Сопроводительное письмо") as HTMLTextAreaElement).value).toBe("Unsaved draft");
      const calls = refresh.mock.calls.length;
      await act(async () => { release(); });
      await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
      expect(refresh.mock.calls.length).toBe(calls);
    } finally {
      unmount();
      vi.useRealTimers();
    }
  });
  it("accepts 84 simultaneous tabs and preserves the value after settings reload", async () => {
    const data = { ...fallback };
    const command = vi.fn(async () => data);
    const { rerender } = render(<BrowserTopicScenarios data={data} command={command} />);
    const input = screen.getByLabelText(/Одновременно вкладок/) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "84" } });
    expect(input.checkValidity()).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Сохранить настройки" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "save-browser-topic-scenario-settings", expect.objectContaining({ concurrency: 84 }),
    ));
    fireEvent.change(input, { target: { value: "2" } });
    rerender(<BrowserTopicScenarios data={{ ...data, browserTopicScenarios: {
      ...data.browserTopicScenarios, concurrency: 84,
    } }} command={command} />);
    expect((screen.getByLabelText(/Одновременно вкладок/) as HTMLInputElement).value).toBe("84");
  });

  it.each(["0", "-1", "1.5", ""])("does not save or launch with invalid concurrency %s", async (value) => {
    const data = { ...fallback, scenarios: [{
      index: 0, productionItemId: "invalid-count-topic", title: "New topic",
      state: "Ожидает", result: "", error: "",
    }] };
    const command = vi.fn(async () => data);
    render(<BrowserTopicScenarios data={data} command={command} />);
    fireEvent.click(screen.getByLabelText("Выбрать: New topic"));
    fireEvent.change(screen.getByLabelText(/Одновременно вкладок/), { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить настройки" }));
    fireEvent.click(screen.getByRole("button", { name: "Создать сценарии в ChatGPT" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/вкладок/));
    expect(command).not.toHaveBeenCalled();
  });

  it("resolves numbered range assignments to durable IDs before saving", async () => {
    const data = {
      ...fallback,
      browserTopicScenarios: { ...fallback.browserTopicScenarios, companionPrompt: "Общий текст." },
      scenarios: [{ index: 0, productionItemId: "prod-one", title: "Первая", state: "Ожидает", result: "", error: "" }, {
        index: 2, productionItemId: "prod-three", title: "Третья", state: "Ожидает", result: "", error: "",
      }],
    };
    const command = vi.fn(async () => data);
    render(<BrowserTopicScenarios data={data} command={command} />);

    expect(screen.getByText("1")).toBeTruthy();
    expect(screen.getByText("3")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Номера тем для диапазона"), { target: { value: "1, 3" } });
    fireEvent.change(screen.getAllByLabelText("Минимум символов")[1], { target: { value: "2000" } });
    fireEvent.change(screen.getAllByLabelText("Максимум символов")[1], { target: { value: "3000" } });
    fireEvent.change(screen.getByLabelText("Дополнительный prompt для диапазона"), { target: { value: "Только для выбранных." } });
    fireEvent.click(screen.getByRole("button", { name: "Применить диапазон" }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить настройки" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith("save-browser-topic-scenario-settings", expect.objectContaining({
      lengthOverrides: {
        "prod-one": { minimum_chars: 2000, maximum_chars: 3000 },
        "prod-three": { minimum_chars: 2000, maximum_chars: 3000 },
      },
      additionalPromptOverrides: { "prod-one": "Только для выбранных.", "prod-three": "Только для выбранных." },
    })));
  });

  it("blocks a rapid duplicate launch while the browser queue is still pending", async () => {
    const data = {
      ...fallback,
      chromeSessions: [{ id: "chatgpt-isolated", label: "ChatGPT isolated", active: true, limitStatus: "available", usage: { ideas: false, scenarios: true, covers: false, seo: false } }],
      browserTopicScenarios: {
        ...fallback.browserTopicScenarios,
        projectUrl: "https://chatgpt.com/g/project",
        sessionId: "chatgpt-isolated",
        companionPrompt: "Только готовый текст.",
      },
      scenarios: [{
        index: 0,
        productionItemId: "production-lock",
        title: "Одна тема",
        state: "Ожидает",
        result: "",
        error: "",
      }],
    };
    let release!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    const command = vi.fn(async (name: string) => {
      if (name === "generate-browser-topic-scenarios") await gate;
      return data;
    });
    render(<BrowserTopicScenarios data={data} command={command} />);

    fireEvent.click(screen.getByLabelText("Выбрать: Одна тема"));
    const runButton = screen.getByRole("button", { name: "Создать сценарии в ChatGPT" }) as HTMLButtonElement;
    fireEvent.click(runButton);

    await waitFor(() => expect(
      command.mock.calls.filter(([name]) => name === "generate-browser-topic-scenarios"),
    ).toHaveLength(1));
    expect(runButton.disabled).toBe(true);

    fireEvent.click(runButton);
    expect(
      command.mock.calls.filter(([name]) => name === "generate-browser-topic-scenarios"),
    ).toHaveLength(1);

    release();
    await waitFor(() => expect(runButton.disabled).toBe(false));
  });

  it("saves and launches selected topics by durable ProductionItem IDs, never previous prose", async () => {
    const data = {
      ...fallback,
      chromeSessions: [{ id: "chatgpt-isolated", label: "ChatGPT isolated", active: true, limitStatus: "available", usage: { ideas: false, scenarios: true, covers: false, seo: false } }],
      browserTopicScenarios: {
        ...fallback.browserTopicScenarios,
        projectUrl: "https://chatgpt.com/g/project",
        sessionId: "chatgpt-isolated",
        companionPrompt: "Только готовый текст.",
      },
      scenarios: [{
        index: 4,
        productionItemId: "production-immutable-4",
        title: "Тема из очереди",
        state: "Ожидает",
        result: "",
        error: "",
      }, {
        index: 5,
        productionItemId: "production-existing-5",
        title: "Тема с готовым текстом",
        state: "Ошибка",
        result: "Старый сценарий не должен оказаться в browser prompt.",
        error: "Старый технический статус",
      }],
    };
    const command = vi.fn(async () => data);
    render(<BrowserTopicScenarios data={data} command={command} />);

    expect(screen.getByText("Тема из очереди")).toBeTruthy();
    expect(screen.getByText("Тема с готовым текстом")).toBeTruthy();
    expect(screen.queryByText("Старый сценарий не должен оказаться в browser prompt.")).toBeNull();
    const existingCheckbox = screen.getByLabelText("Выбрать: Тема с готовым текстом") as HTMLInputElement;
    expect(existingCheckbox.disabled).toBe(true);

    fireEvent.click(screen.getByLabelText("Выбрать: Тема из очереди"));
    const runButton = screen.getByRole("button", { name: "Создать сценарии в ChatGPT" }) as HTMLButtonElement;
    await waitFor(() => expect(runButton.disabled).toBe(false));
    fireEvent.click(runButton);

    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "generate-browser-topic-scenarios",
      { indices: [4], productionItemIds: ["production-immutable-4"], batchId: expect.any(String) },
    ));
    expect(command).toHaveBeenCalledWith("save-browser-topic-scenario-settings", expect.objectContaining({
      projectUrl: "https://chatgpt.com/g/project",
      sessionId: "chatgpt-isolated",
    }));
  });
});
