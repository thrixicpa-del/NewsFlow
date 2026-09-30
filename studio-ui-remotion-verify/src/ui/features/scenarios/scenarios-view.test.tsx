import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { fallback, FinishedScripts, Scenarios } from "../../App";

describe("Scenarios and scripts Light views", () => {
  it("offers explicit recovery for persisted active scenarios and keeps recovered errors in the normal retry count", () => {
    const command = vi.fn();
    const data = {
      ...fallback,
      scenarios: [
        { index: 0, title: "Прерванный", state: "В обработке", result: "Частичный текст", error: "" },
        { index: 1, title: "Восстановленный", state: "Ошибка", result: "Частичный текст", error: "Прервана" },
      ],
    };
    render(<Scenarios data={data} go={vi.fn()} command={command} refresh={async () => undefined} />);

    fireEvent.click(screen.getByRole("button", { name: "Восстановить прерванные: 1" }));

    expect(command).toHaveBeenCalledWith("reconcile-runtime-state");
    expect(screen.getByRole("button", { name: "Написать все сценарии: 1" })).not.toBeNull();
  });

  it("does not offer persisted-active recovery while this renderer is generating", () => {
    const command = vi.fn(() => new Promise<typeof fallback>(() => {}));
    const data = {
      ...fallback,
      scenarios: [
        { index: 0, title: "Прерванный", state: "В обработке", result: "Частичный текст", error: "" },
        { index: 1, title: "Ожидающий", state: "Ожидает", result: "", error: "" },
      ],
    };
    render(<Scenarios data={data} go={vi.fn()} command={command} refresh={async () => undefined} />);

    fireEvent.click(screen.getByRole("button", { name: "Написать все сценарии: 1" }));

    expect(screen.queryByRole("button", { name: "Восстановить прерванные: 1" })).toBeNull();
  });

  it("uses the workstation scenario queue table without changing the selected-write command", () => {
    const command = vi.fn();
    const data = {
      ...fallback,
      scenarios: [{ index: 0, title: "Ормуз", state: "Ожидает", result: "", error: "" }],
    };
    render(<Scenarios data={data} go={vi.fn()} command={command} refresh={async () => undefined} />);

    expect(screen.getByRole("table", { name: "Очередь сценариев" })).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Ормуз" }));
    fireEvent.click(screen.getByRole("button", { name: "Написать выбранные" }));
    expect(command).toHaveBeenCalledWith("generate-scenarios", { indices: [0], provider: "agent" });
  });

  it("sends the ChatGPT direct provider in the selected-scenarios command", () => {
    const command = vi.fn();
    const data = {
      ...fallback,
      scenarios: [{ index: 0, title: "Проверочная тема", state: "Ожидает", result: "", error: "" }],
    };
    render(<Scenarios data={data} go={vi.fn()} command={command} refresh={async () => undefined} />);

    fireEvent.change(screen.getByLabelText("Исполнитель сценария"), { target: { value: "openai" } });
    fireEvent.click(screen.getByRole("button", { name: "Проверочная тема" }));
    fireEvent.click(screen.getByRole("button", { name: "Написать выбранные" }));

    expect(command).toHaveBeenCalledWith("generate-scenarios", {
      indices: [0],
      provider: "openai",
    });
  });

  it("rewrites only selected ready scenarios through the force command", () => {
    const command = vi.fn();
    const data = {
      ...fallback,
      scenarios: [
        { index: 0, title: "Переписать", state: "Готово", result: "Старый текст", error: "" },
        { index: 1, title: "Не трогать", state: "Готово", result: "Другой текст", error: "" },
      ],
    };
    render(<Scenarios data={data} go={vi.fn()} command={command} refresh={async () => undefined} />);

    fireEvent.click(screen.getByRole("button", { name: "Переписать" }));
    fireEvent.click(screen.getByRole("button", { name: "Переписать выбранные" }));

    expect(command).toHaveBeenCalledWith("generate-scenarios", {
      indices: [0],
      provider: "agent",
      force: true,
    });
  });

  it("writes every unfinished scenario through the current batch command without resubmitting ready rows", () => {
    const command = vi.fn();
    const data = {
      ...fallback,
      scenarios: [
        { index: 0, title: "Готовый", state: "Готово", result: "Текст", error: "" },
        { index: 1, title: "Нужно написать", state: "Ожидает", result: "", error: "" },
      ],
    };
    render(<Scenarios data={data} go={vi.fn()} command={command} refresh={async () => undefined} />);

    fireEvent.click(screen.getByRole("button", { name: "Написать все сценарии: 1" }));

    expect(command).toHaveBeenCalledWith("generate-scenarios", { provider: "agent" });
  });

  it("offers a batch retry for a length-paused scenario without calling it ready", () => {
    const command = vi.fn();
    const data = {
      ...fallback,
      scenarios: [
        {
          index: 0,
          title: "Нужна корректировка длины",
          state: "Нужно действие",
          result: "Короткий текст",
          error: "",
          lengthStatus: "SHORT" as const,
          actualChars: 6110,
          allowedMin: 9000,
          allowedMax: 120000,
          lengthRepairAttempts: 2,
        },
      ],
    };
    render(<Scenarios data={data} go={vi.fn()} command={command} refresh={async () => undefined} />);

    fireEvent.click(screen.getByRole("button", { name: "Написать все сценарии: 1" }));

    expect(command).toHaveBeenCalledWith("generate-scenarios", { provider: "agent" });
    expect(screen.getByText(/Длина SHORT: 6110 знаков/)).not.toBeNull();
    expect(screen.queryByRole("button", { name: "Все сценарии готовы" })).toBeNull();
  });

  it("submits selected generation once and disables both generation buttons while pending", () => {
    const command = vi.fn(() => new Promise<typeof fallback>(() => {}));
    const data = {
      ...fallback,
      scenarios: [{ index: 0, title: "Ожидающий", state: "Ожидает", result: "", error: "" }],
    };
    render(<Scenarios data={data} go={vi.fn()} command={command} refresh={async () => undefined} />);

    fireEvent.click(screen.getByRole("button", { name: "Ожидающий" }));
    const selected = screen.getByRole("button", { name: "Написать выбранные" });
    const all = screen.getByRole("button", { name: "Написать все сценарии: 1" });
    act(() => {
      fireEvent.click(selected);
      fireEvent.click(selected);
    });

    expect(command).toHaveBeenCalledTimes(1);
    expect(command).toHaveBeenCalledWith("generate-scenarios", { indices: [0], provider: "agent" });
    expect(selected).toHaveProperty("disabled", true);
    expect(all).toHaveProperty("disabled", true);
  });

  it("shares the generation lock between selected and all-scenarios actions", () => {
    const command = vi.fn(() => new Promise<typeof fallback>(() => {}));
    const data = {
      ...fallback,
      scenarios: [
        { index: 0, title: "Первый", state: "Ожидает", result: "", error: "" },
        { index: 1, title: "Второй", state: "Ожидает", result: "", error: "" },
      ],
    };
    render(<Scenarios data={data} go={vi.fn()} command={command} refresh={async () => undefined} />);

    fireEvent.click(screen.getByRole("button", { name: "Первый" }));
    const selected = screen.getByRole("button", { name: "Написать выбранные" });
    const all = screen.getByRole("button", { name: "Написать все сценарии: 2" });
    act(() => {
      fireEvent.click(selected);
      fireEvent.click(all);
    });

    expect(command).toHaveBeenCalledTimes(1);
    expect(command).toHaveBeenCalledWith("generate-scenarios", { indices: [0], provider: "agent" });
  });

  it("keeps add, generate and finished-script navigation contracts", () => {
    const command = vi.fn();
    const go = vi.fn();
    const data = {
      ...fallback,
      scenarios: [{ index: 0, title: "Ормуз", state: "Ожидает", result: "", error: "" }],
    };
    render(<Scenarios data={data} go={go} command={command} refresh={async () => undefined} />);

    fireEvent.change(screen.getByLabelText("Идеи для сценариев"), { target: { value: "Новая тема" } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить сценарии" }));
    fireEvent.click(screen.getByRole("button", { name: /Ормуз/ }));
    fireEvent.click(screen.getByRole("button", { name: "Написать выбранные" }));
    fireEvent.click(screen.getByRole("button", { name: /Готовые сценарии/ }));

    expect(command).toHaveBeenCalledWith("add-scenarios", { titles: "Новая тема" });
    expect(command).toHaveBeenCalledWith("generate-scenarios", { indices: [0], provider: "agent" });
    expect(go).toHaveBeenCalledWith("scripts");
  });

  it("renames a selected scenario through an in-app dialog", async () => {
    const command = vi.fn().mockResolvedValue(fallback);
    const data = {
      ...fallback,
      scenarios: [{ index: 0, title: "Старая тема", state: "Ожидает", result: "", error: "" }],
    };
    render(<Scenarios data={data} go={vi.fn()} command={command} refresh={async () => undefined} />);

    fireEvent.click(screen.getByRole("button", { name: "Старая тема" }));
    fireEvent.click(screen.getByRole("button", { name: "Изменить тему" }));
    expect(screen.getByRole("dialog", { name: "Изменить тему сценария" })).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Новое название сценария"), {
      target: { value: "Новая тема" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить название" }));

    await waitFor(() =>
      expect(command).toHaveBeenCalledWith("rename-scenario", { index: 0, title: "Новая тема" }),
    );
  });

  it("preserves manual import fields when the import command fails", async () => {
    const command = vi.fn().mockResolvedValue(undefined);
    render(<Scenarios data={fallback} go={vi.fn()} command={command} refresh={async () => undefined} />);

    fireEvent.change(screen.getByLabelText("Название сценария"), { target: { value: "Ручной заголовок" } });
    fireEvent.change(screen.getByLabelText("Полный текст сценария"), { target: { value: "Ручной текст" } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить своё" }));

    await waitFor(() =>
      expect(command).toHaveBeenCalledWith("import-manual-scenario", {
        title: "Ручной заголовок",
        text: "Ручной текст",
      }),
    );
    expect((screen.getByLabelText("Название сценария") as HTMLInputElement).value).toBe("Ручной заголовок");
    expect((screen.getByLabelText("Полный текст сценария") as HTMLTextAreaElement).value).toBe("Ручной текст");
  });

  it("clears manual import fields only after a successful import", async () => {
    const command = vi.fn().mockResolvedValue(fallback);
    render(<Scenarios data={fallback} go={vi.fn()} command={command} refresh={async () => undefined} />);

    fireEvent.change(screen.getByLabelText("Название сценария"), { target: { value: "Ручной заголовок" } });
    fireEvent.change(screen.getByLabelText("Полный текст сценария"), { target: { value: "Ручной текст" } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить своё" }));

    await waitFor(() =>
      expect(command).toHaveBeenCalledWith("import-manual-scenario", {
        title: "Ручной заголовок",
        text: "Ручной текст",
      }),
    );
    await waitFor(() => expect((screen.getByLabelText("Название сценария") as HTMLInputElement).value).toBe(""));
    expect((screen.getByLabelText("Полный текст сценария") as HTMLTextAreaElement).value).toBe("");
  });

  it("keeps ready-file import active and requires a title and text for manual import", async () => {
    const chooseScenarioTexts = vi.fn().mockResolvedValue([]);
    Object.assign(window, { newsflowDesktop: { chooseScenarioTexts } });
    render(<Scenarios data={fallback} go={vi.fn()} command={vi.fn()} refresh={async () => undefined} />);

    const readyFileImport = screen.getByRole("button", { name: "Добавить готовый" });
    const manualSubmit = screen.getByRole("button", { name: "Добавить своё" });
    expect(readyFileImport).toHaveProperty("disabled", false);
    expect(manualSubmit).toHaveProperty("disabled", true);
    fireEvent.click(readyFileImport);
    await waitFor(() => expect(chooseScenarioTexts).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText("Название сценария"), { target: { value: "Ручной заголовок" } });
    expect(manualSubmit).toHaveProperty("disabled", true);

    fireEvent.change(screen.getByLabelText("Полный текст сценария"), { target: { value: "Ручной текст" } });
    expect(manualSubmit).toHaveProperty("disabled", false);
  });

  it("imports file-selected ready scenarios through the existing batch command", async () => {
    const command = vi.fn().mockResolvedValue(fallback);
    const chooseScenarioTexts = vi.fn().mockResolvedValue([
      { title: "Сценарий из TXT", text: "Текст из файла" },
      { title: "Сценарий из ZIP", text: "Текст из архива" },
    ]);
    Object.assign(window, { newsflowDesktop: { chooseScenarioTexts } });
    render(<Scenarios data={fallback} go={vi.fn()} command={command} refresh={async () => undefined} />);

    fireEvent.click(screen.getByRole("button", { name: "Добавить готовый" }));

    await waitFor(() =>
      expect(command).toHaveBeenCalledWith("import-manual-scenarios", {
        items: [
          { title: "Сценарий из TXT", text: "Текст из файла" },
          { title: "Сценарий из ZIP", text: "Текст из архива" },
        ],
      }),
    );
  });

  it("submits manual import once and disables its button while pending", () => {
    const command = vi.fn(() => new Promise<typeof fallback>(() => {}));
    render(<Scenarios data={fallback} go={vi.fn()} command={command} refresh={async () => undefined} />);

    fireEvent.change(screen.getByLabelText("Название сценария"), { target: { value: "Ручной заголовок" } });
    fireEvent.change(screen.getByLabelText("Полный текст сценария"), { target: { value: "Ручной текст" } });
    const submit = screen.getByRole("button", { name: "Добавить своё" });
    act(() => {
      fireEvent.click(submit);
      fireEvent.click(submit);
    });

    expect(command).toHaveBeenCalledTimes(1);
    expect(command).toHaveBeenCalledWith("import-manual-scenario", {
      title: "Ручной заголовок",
      text: "Ручной текст",
    });
    expect(submit).toHaveProperty("disabled", true);
  });

  it("keeps transfer of a ready script on the current command", () => {
    const command = vi.fn();
    const go = vi.fn();
    const data = {
      ...fallback,
      scenarios: [{ index: 4, title: "Готовый материал", state: "Готово", result: "Полный текст", error: "" }],
    };
    render(<FinishedScripts data={data} go={go} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: /В обложки/ }));
    expect(command).toHaveBeenCalledWith("transfer-scenarios", { target: "covers", indices: [4], requireCompleted: true });
  });

  it("uses a ready-script workbench table before opening the current writing desk", () => {
    const data = {
      ...fallback,
      scenarios: [{ index: 4, title: "Готовый материал", state: "Готово", result: "Полный текст", error: "" }],
    };
    render(<FinishedScripts data={data} go={vi.fn()} command={vi.fn()} />);

    expect(screen.getByRole("table", { name: "Готовые сценарии" })).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Развернуть" }));
    expect(screen.getByRole("dialog", { name: "Рабочий текст сценария" })).not.toBeNull();
  });

  it("protects an edited script before closing its writing desk", () => {
    const command = vi.fn();
    const go = vi.fn();
    const data = {
      ...fallback,
      scenarios: [{ index: 4, title: "Готовый материал", state: "Готово", result: "Полный текст", error: "" }],
    };
    render(<FinishedScripts data={data} go={go} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "Развернуть" }));
    fireEvent.change(screen.getByLabelText("Текст сценария: Готовый материал"), {
      target: { value: "Изменённый текст" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Свернуть" }));

    expect(screen.getByRole("dialog", { name: "Несохранённые изменения" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Продолжить редактирование" }));
    expect((screen.getByLabelText("Текст сценария: Готовый материал") as HTMLTextAreaElement).value).toBe("Изменённый текст");
    expect(command).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Свернуть" }));
    fireEvent.click(screen.getByRole("button", { name: "Не сохранять" }));
    expect(screen.queryByLabelText("Текст сценария: Готовый материал")).toBeNull();
    expect(command).not.toHaveBeenCalled();
  });

  it("saves the edited script through the current command from Ctrl+S", () => {
    const command = vi.fn().mockResolvedValue(fallback);
    const go = vi.fn();
    const data = {
      ...fallback,
      scenarios: [{ index: 4, title: "Готовый материал", state: "Готово", result: "Полный текст", error: "" }],
    };
    render(<FinishedScripts data={data} go={go} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "Развернуть" }));
    fireEvent.change(screen.getByLabelText("Текст сценария: Готовый материал"), {
      target: { value: "Изменённый текст" },
    });
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });

    expect(command).toHaveBeenCalledWith("save-scenario-text", {
      index: 4,
      text: "Изменённый текст",
    });
  });
});
