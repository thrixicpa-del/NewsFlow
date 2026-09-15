import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TaskCenter } from "./TaskCenter";

describe("TaskCenter", () => {
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
