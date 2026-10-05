import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { App, Editor, fallback, Outputs } from "../../App";

describe("Montage Light view", () => {
  it("keeps the current montage controls in the Fast Editing workspace", () => {
    render(<Editor data={fallback} command={vi.fn()} refresh={async () => undefined} />);

    expect(screen.getByLabelText("Fast Editing workspace")).toBeTruthy();
  });

  it("shows persisted semantic fallback and reuse diagnostics in the timeline", () => {
    const data = {
      ...fallback,
      montageProjects: [{
        title: "Ормуз — похожая тема",
        path: "D:/projects/hormuz.newsflow",
        duration: 12,
        selectionSummaryText: "2 сцен · strict 1 · semantic 0 · reuse 1",
        clips: [{
          path: "D:/footage/tanker.mp4",
          duration: 6,
          narration: "Танкер проходит пролив",
          source: "local · SAFE_REUSE",
          sourceStart: 8,
          fallbackLevel: "SAFE_REUSE",
          sourceFamily: "tanker-family",
          reused: true,
          positionBucket: "MIDDLE",
          positionRotationReason: "другой сегмент длинного источника",
        }],
      }],
    } as NewsFlowSnapshot;

    render(<Editor data={data} command={vi.fn()} refresh={async () => undefined} />);

    expect(screen.getByText("2 сцен · strict 1 · semantic 0 · reuse 1")).toBeTruthy();
    expect(screen.getByText(/SAFE_REUSE · MIDDLE · start 8\.0 c/)).toBeTruthy();
    expect(screen.queryByText(/Не найдено ни одного допустимого футажа/)).toBeNull();
  });

  it("keeps advanced montage configuration in a focused workspace drawer", () => {
    render(<Editor data={fallback} command={vi.fn()} refresh={async () => undefined} />);

    expect(screen.getAllByText("Монтаж сейчас")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Настроить монтаж" })).toBeTruthy();
    expect(screen.queryByText("Как собрать и передать монтаж")).toBeNull();
  });

  it("shows the no-English-text rule as mandatory", () => {
    render(<Editor data={fallback} command={vi.fn()} refresh={async () => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Настроить монтаж" }));

    const guard = screen.getByRole("checkbox", {
      name: /Не использовать футажи с английскими\/латинскими надписями/,
    }) as HTMLInputElement;
    expect(guard.checked).toBe(true);
    expect(guard.disabled).toBe(true);
    expect(
      screen.getByText(/Если готовый сценарий есть, NewsFlow всегда использует смысл каждой реплики/),
    ).toBeTruthy();
  });

  it("keeps the current fast montage queue contract", async () => {
    const data = {
      ...fallback,
      scenarios: [{ index: 1, title: "Ормуз", state: "Готово", result: "Текст", error: "" }],
      voiceItems: [{ index: 1, title: "Ормуз", state: "Готово", path: "D:/voice.mp3" }],
    };
    const command = vi.fn(async () => data);
    render(<Editor data={data} command={command} refresh={async () => undefined} />);

    fireEvent.click(screen.getByRole("button", { name: /Ормуз/ }));
    fireEvent.click(screen.getByRole("button", { name: "Собрать выбранные" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("run-montage-queue", { indices: [1], replaceOutput: false }));
  });

  it("does not submit the current montage launch twice while settings are pending", async () => {
    let releaseSettings: (() => void) | undefined;
    const data = {
      ...fallback,
      scenarios: [{ index: 1, title: "Ормуз", state: "Готово", result: "Текст", error: "" }],
      voiceItems: [{ index: 1, title: "Ормуз", state: "Готово", path: "D:/voice.mp3" }],
    };
    const command = vi.fn(() => new Promise<NewsFlowSnapshot | undefined>((resolve) => {
      releaseSettings = () => resolve(undefined);
    }));
    render(<Editor data={data} command={command} refresh={async () => undefined} />);

    fireEvent.click(screen.getByRole("button", { name: /Ормуз/ }));
    const launch = screen.getByRole("button", { name: "Собрать выбранные" });
    fireEvent.click(launch);
    fireEvent.click(launch);

    await Promise.resolve();
    expect(command).toHaveBeenCalledTimes(1);
    expect(command).toHaveBeenCalledWith("save-montage-settings", expect.any(Object));
    releaseSettings?.();
  });

  it("does not submit the montage queue twice while the queue command is pending", async () => {
    let releaseQueue: (() => void) | undefined;
    const data = {
      ...fallback,
      scenarios: [{ index: 1, title: "Ормуз", state: "Готово", result: "Текст", error: "" }],
      voiceItems: [{ index: 1, title: "Ормуз", state: "Готово", path: "D:/voice.mp3" }],
    };
    const command = vi.fn((name: string) => {
      if (name === "save-montage-settings") return Promise.resolve(data);
      return new Promise<NewsFlowSnapshot | undefined>((resolve) => {
        releaseQueue = () => resolve(data);
      });
    });
    render(<Editor data={data} command={command} refresh={async () => undefined} />);

    fireEvent.click(screen.getByRole("button", { name: /Ормуз/ }));
    const launch = screen.getByRole("button", { name: "Собрать выбранные" });
    fireEvent.click(launch);
    await waitFor(() => expect(command).toHaveBeenCalledWith("run-montage-queue", { indices: [1], replaceOutput: false }));
    fireEvent.click(launch);

    expect(command.mock.calls.filter(([name]) => name === "run-montage-queue")).toHaveLength(1);
    expect(launch.hasAttribute("disabled")).toBe(true);
    releaseQueue?.();
  });

  it("submits exactly the ctrl-selected montage rows", async () => {
    const data = {
      ...fallback,
      scenarios: [
        { index: 1, title: "Первая", state: "Готово", result: "Текст 1", error: "" },
        { index: 2, title: "Вторая", state: "Готово", result: "Текст 2", error: "" },
        { index: 3, title: "Третья", state: "Готово", result: "Текст 3", error: "" },
      ],
      voiceItems: [
        { index: 1, title: "Первая", state: "Готово", path: "D:/1.mp3" },
        { index: 2, title: "Вторая", state: "Готово", path: "D:/2.mp3" },
        { index: 3, title: "Третья", state: "Готово", path: "D:/3.mp3" },
      ],
    };
    const command = vi.fn().mockResolvedValue(data);
    render(<Editor data={data} command={command} refresh={async () => undefined} />);

    fireEvent.click(screen.getByRole("button", { name: /Первая/ }));
    fireEvent.click(screen.getByRole("button", { name: /Третья/ }), { ctrlKey: true });
    fireEvent.click(screen.getByRole("button", { name: "Собрать выбранные" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "run-montage-queue", { indices: [1, 3], replaceOutput: false },
    ));
  });

  it("keeps empty selected actions disabled and normal launch excludes ready rows", async () => {
    const data = {
      ...fallback,
      scenarios: [
        { index: 1, title: "Готовая", state: "Готово", result: "Текст 1", error: "" },
        { index: 2, title: "Новая", state: "Готово", result: "Текст 2", error: "" },
      ],
      voiceItems: [
        { index: 1, title: "Готовая", state: "Готово", path: "D:/1.mp3" },
        { index: 2, title: "Новая", state: "Готово", path: "D:/2.mp3" },
      ],
      montageTasks: [
        { index: 1, title: "Готовая", status: "Готово", outputPath: "D:/ready.mp4" },
        { index: 2, title: "Новая", status: "Готов к монтажу", outputPath: "" },
      ],
    };
    const command = vi.fn().mockResolvedValue(data);
    render(<Editor data={data} command={command} refresh={async () => undefined} />);

    const selected = screen.getByRole("button", { name: "Собрать выбранные" });
    expect(selected.hasAttribute("disabled")).toBe(true);
    fireEvent.click(selected);
    expect(command).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Собрать незавершённые" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "run-montage-queue", { indices: [2], replaceOutput: false },
    ));
  });

  it("keeps an interrupted text-check row visible and resumable in the montage queue", async () => {
    const data = {
      ...fallback,
      scenarios: [{ index: 83, title: "Последняя ручная тема", state: "Готово", result: "Мой текст", error: "" }],
      voiceItems: [{ index: 83, title: "Последняя ручная тема", state: "Готово", path: "D:/084.mp3" }],
      montageTasks: [{
        index: 83,
        title: "Последняя ручная тема",
        status: "Проверка текста",
        phase: "Проверка текста",
        outputPath: "",
      }],
    };
    const command = vi.fn().mockResolvedValue(data);
    render(<Editor data={data} command={command} refresh={async () => undefined} />);

    expect(screen.getByRole("button", { name: /Последняя ручная тема/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Собрать незавершённые" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "run-montage-queue", { indices: [83], replaceOutput: false },
    ));
  });

  it("offers explicit selected retry for an error row", async () => {
    const data = {
      ...fallback,
      scenarios: [{ index: 1, title: "Ошибка", state: "Готово", result: "Текст", error: "" }],
      voiceItems: [{ index: 1, title: "Ошибка", state: "Готово", path: "D:/voice.mp3" }],
      montageTasks: [{ index: 1, title: "Ошибка", status: "Ошибка", error: "FFmpeg failed", outputPath: "" }],
    };
    const command = vi.fn().mockResolvedValue(data);
    render(<Editor data={data} command={command} refresh={async () => undefined} />);

    fireEvent.click(screen.getByRole("button", { name: /Ошибка/ }));
    const retry = screen.getByRole("button", { name: "Повторить монтаж выбранных" });
    expect(retry.hasAttribute("disabled")).toBe(false);
    fireEvent.click(retry);

    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "run-montage-queue", { indices: [1], replaceOutput: true },
    ));
  });

  it("keeps pause and continue controls truthful", async () => {
    const running = {
      ...fallback,
      montageTasks: [{ index: 1, title: "Тема", status: "Рендер", outputPath: "" }],
      montageSettings: { ...fallback.montageSettings, queuePaused: false },
    };
    const pauseCommand = vi.fn().mockResolvedValue(running);
    const first = render(<Editor data={running} command={pauseCommand} refresh={async () => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Пауза" }));
    expect(pauseCommand).toHaveBeenCalledWith("save-montage-settings", { queuePaused: true });
    first.unmount();

    const paused = { ...running, montageSettings: { ...running.montageSettings, queuePaused: true } };
    const continueCommand = vi.fn().mockResolvedValue(paused);
    render(<Editor data={paused} command={continueCommand} refresh={async () => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Продолжить" }));
    expect(continueCommand).toHaveBeenCalledWith("save-montage-settings", { queuePaused: false });
  });

  it("distinguishes selected MP4 cleanup from explicit all cleanup", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const data = {
      ...fallback,
      scenarios: [{ index: 1, title: "Ормуз", state: "Готово", result: "Текст", error: "" }],
      voiceItems: [{ index: 1, title: "Ормуз", state: "Готово", path: "D:/voice.mp3" }],
      montageTasks: [{ index: 1, title: "Ормуз", status: "Готово", outputPath: "D:/result.mp4" }],
    };
    const command = vi.fn().mockResolvedValue(data);
    render(<Editor data={data} command={command} refresh={async () => undefined} />);

    const selectedDelete = screen.getByRole("button", { name: "Удалить выбранные MP4" });
    expect(selectedDelete.hasAttribute("disabled")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: /Ормуз/ }));
    fireEvent.click(selectedDelete);
    await waitFor(() => expect(command).toHaveBeenCalledWith("remove-montage-results", { indices: [1] }));

    fireEvent.click(screen.getByRole("button", { name: "Удалить все MP4" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("remove-montage-results", { all: true }));
    confirm.mockRestore();
  });

  it("confirms and sends bulk MP4 deletion through the current command", async () => {
    const command = vi.fn().mockResolvedValue(fallback);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const data = {
      ...fallback,
      montageTasks: [{ index: 1, title: "Ормуз", status: "Готово", outputPath: "D:/results/ormuz.mp4" }],
    };
    render(<Editor data={data} command={command} refresh={async () => undefined} />);

    fireEvent.click(screen.getByRole("button", { name: "Удалить все MP4" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith("remove-montage-results", { all: true }));
    confirm.mockRestore();
  });

  it("keeps Results focused on the manual batch export instead of legacy publication packages", () => {
    const data = { ...fallback, outputs: [{ folder: "D:/results/ormuz", video: "D:/results/ormuz/video.mp4" }] };
    render(<Outputs data={data} command={vi.fn()} />);

    expect(screen.getByLabelText("Output Artifact Index")).toBeTruthy();
    expect(screen.queryByRole("table", { name: "Готовые пакеты роликов" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Собрать пакеты для публикации" })).toBeNull();
    expect(screen.getByRole("button", { name: "Собрать результаты" })).toBeTruthy();
  });

  it("shows only snapshot-backed provenance when an MP4 task is inspected", () => {
    const data = {
      ...fallback,
      montageTasks: [{
        index: 1,
        title: "Ормуз",
        status: "Готово",
        phase: "Экспорт",
        updatedAt: "2026-09-15T12:00:00Z",
        voicePath: "D:/voice.mp3",
        outputPath: "D:/result.mp4",
        projectPath: "D:/plan.json",
      }],
    };
    render(<Editor data={data} command={vi.fn()} refresh={async () => undefined} />);

    fireEvent.click(screen.getByRole("button", { name: "Инспектор MP4" }));

    expect(screen.getByRole("heading", { name: "Инспектор MP4" })).toBeTruthy();
    expect(screen.getByText("D:/result.mp4")).toBeTruthy();
    expect(screen.getByText("Текущий snapshot не сообщает ProductionItem ID")).toBeTruthy();
    expect(screen.getByText("Текущий snapshot не сообщает признак устаревания")).toBeTruthy();
  });

  it("renders one live-status ribbon for the active montage route", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "ПРОИЗВОДСТВО" }));
    fireEvent.click(screen.getByRole("button", { name: "Монтаж" }));

    expect(screen.getAllByText("Монтаж сейчас")).toHaveLength(1);
  });
});
