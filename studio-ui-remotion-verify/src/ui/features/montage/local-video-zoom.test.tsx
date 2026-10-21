import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Editor, fallback } from "../../App";

describe("Optional local video zoom", () => {
  it("defaults off, saves the choice and does not restart selection", async () => {
    const command = vi.fn().mockResolvedValue(fallback);
    render(<Editor data={fallback} command={command} refresh={async () => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Настроить монтаж" }));
    const checkbox = screen.getByRole("checkbox", { name: "Плавное приближение локальных видео" }) as HTMLInputElement;
    expect(checkbox.checked).toBe(false);
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: "Сохранить выбор" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-montage-settings", expect.objectContaining({ localVideoZoom: true })));
    expect(command).toHaveBeenCalledTimes(1);
  });

  it("keeps a saved choice when starting the queue", async () => {
    const data = { ...fallback, montageSettings: { ...fallback.montageSettings, localVideoZoom: true },
      scenarios: [{ index: 1, title: "Test", state: "Готово", result: "Text", error: "" }],
      voiceItems: [{ index: 1, title: "Test", state: "Готово", path: "D:/synthetic.mp3" }] };
    const command = vi.fn().mockResolvedValue(data);
    render(<Editor data={data} command={command} refresh={async () => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Собрать незавершённые" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-montage-settings", expect.objectContaining({ localVideoZoom: true })));
    await waitFor(() => expect(command).toHaveBeenCalledWith("run-montage-queue", { indices: [1], replaceOutput: false }));
  });

  it("exports the saved plan with an explicit zoom choice and never requests selection", async () => {
    const data = { ...fallback,
      voiceItems: [{ index: 1, title: "Saved plan", state: "Готово", path: "D:/synthetic.mp3" }],
      scenarios: [{ index: 1, title: "Saved plan", state: "Готово", result: "Text", error: "" }],
      montageTasks: [{ index: 1, title: "Saved plan", status: "Готово", projectPath: "D:/saved.newsflow", outputPath: "D:/saved.mp4" }],
    };
    const command = vi.fn().mockResolvedValue(data);
    render(<Editor data={data} command={command} refresh={async () => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: /Saved plan.*synthetic.mp3/ }));
    fireEvent.click(screen.getByRole("button", { name: "Настроить монтаж" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Плавное приближение локальных видео" }));
    fireEvent.click(screen.getByRole("button", { name: "Повторный экспорт с выбранным приближением" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("run-montage-queue", {
      indices: [1], renderOnly: true, localVideoZoom: true,
    }));
    expect(command).toHaveBeenCalledTimes(1);
  });
});
