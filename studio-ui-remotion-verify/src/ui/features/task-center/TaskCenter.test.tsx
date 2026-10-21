import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TaskCenter } from "./TaskCenter";

describe("TaskCenter", () => {
  it("shows active voice and montage together while the source script is ready", () => {
    render(<TaskCenter data={{
      scenarios: [{ index: 0, title: "Script", state: "Готово", result: "Text", error: "" }], covers: [],
      voiceItems: [{ index: 0, title: "Voice", state: "Готово", path: "", voiceStatus: "VoiceGen: выполняется", voiceProgress: 55 }],
      montageTasks: [{ index: 1, title: "Montage", status: "Рендер", progress: 40 }],
      publication: { v2: { queue: [] } },
    } as unknown as NewsFlowSnapshot} />);
    expect(screen.getByRole("button", { name: "Открыть задачу: Voice" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Открыть задачу: Montage" })).toBeTruthy();
    expect(screen.getByText("В работе: 2 · ошибок: 0 · готово: 1")).toBeTruthy();
  });

  it("opens the caller-owned inspector context for a selected active task", () => {
    const onSelect = vi.fn();
    render(<TaskCenter data={{
      scenarios: [],
      covers: [{ title: "Обложка", status: "Генерация", progress: 40 }],
      voiceItems: [], montageTasks: [], publication: { v2: { queue: [] } },
    } as unknown as NewsFlowSnapshot} onSelect={onSelect} />);

    fireEvent.click(screen.getByRole("button", { name: /Обложка/ }));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ source: "cover", status: "RUNNING", title: "Обложка" }));
  });
});
