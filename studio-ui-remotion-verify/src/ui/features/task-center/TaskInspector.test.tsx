import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TaskInspector } from "./TaskInspector";

describe("TaskInspector", () => {
  it("shows current task provenance without inferring an artifact that is absent", () => {
    const onClose = vi.fn();
    render(<TaskInspector entry={{ id: "voice-p-1", source: "voice", title: "Озвучка", status: "WAITING", detail: "Ожидание провайдера" }} onClose={onClose} />);

    expect(screen.getByRole("dialog").textContent).toContain("Озвучка");
    expect(screen.getByText("Ожидает провайдера")).not.toBeNull();
    expect(screen.getByText("Источник").parentElement?.textContent).toContain("voice");
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
