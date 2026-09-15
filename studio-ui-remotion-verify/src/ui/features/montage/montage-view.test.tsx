import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { App, Editor, fallback, Outputs } from "../../App";

describe("Montage Light view", () => {
  it("keeps the current montage controls in the Fast Editing workspace", () => {
    render(<Editor data={fallback} command={vi.fn()} refresh={async () => undefined} />);

    expect(screen.getByLabelText("Fast Editing workspace")).toBeTruthy();
  });

  it("keeps advanced montage configuration in a focused workspace drawer", () => {
    render(<Editor data={fallback} command={vi.fn()} refresh={async () => undefined} />);

    expect(screen.getAllByText("Монтаж сейчас")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Настроить монтаж" })).toBeTruthy();
    expect(screen.queryByText("Как собрать и передать монтаж")).toBeNull();
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

  it("keeps completed output packages in a durable artifact index", () => {
    const data = { ...fallback, outputs: [{ folder: "D:/results/ormuz", video: "D:/results/ormuz/video.mp4" }] };
    render(<Outputs data={data} command={vi.fn()} />);

    expect(screen.getByLabelText("Output Artifact Index")).toBeTruthy();
    expect(screen.getByRole("table", { name: "Готовые пакеты роликов" })).toBeTruthy();
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
