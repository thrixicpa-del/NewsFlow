import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ContextInspector } from "./ContextInspector";

describe("ContextInspector", () => {
  it("shows selected queue context and persists layout sizing through its caller", () => {
    const onWidthChange = vi.fn();
    render(<ContextInspector entry={{ id: "montage-p-1", source: "montage", title: "Монтаж Ормуз", status: "RUNNING", detail: "Рендер", progress: 48 }} width={360} density="comfortable" onDensityChange={vi.fn()} onWidthChange={onWidthChange} onClose={vi.fn()} onHide={vi.fn()} />);

    expect(screen.getByLabelText("Контекстный инспектор").textContent).toContain("Монтаж Ормуз");
    fireEvent.change(screen.getByLabelText("Ширина инспектора"), { target: { value: "420" } });
    expect(onWidthChange).toHaveBeenCalledWith(420);
  });

  it("lets the operator hide the inspector without closing the selected task", () => {
    const onHide = vi.fn();
    const onClose = vi.fn();
    render(<ContextInspector entry={{ id: "cover-1", source: "cover", title: "Обложка", status: "WAITING", detail: "Ожидает" }} width={360} density="comfortable" onDensityChange={vi.fn()} onWidthChange={vi.fn()} onClose={onClose} onHide={onHide} />);

    fireEvent.click(screen.getByRole("button", { name: "Скрыть инспектор" }));
    expect(onHide).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("lets the caller switch the workstation to compact density", () => {
    const onDensityChange = vi.fn();
    render(<ContextInspector entry={null} width={360} density="comfortable" onDensityChange={onDensityChange} onWidthChange={vi.fn()} onClose={vi.fn()} onHide={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Компактный режим" }));
    expect(onDensityChange).toHaveBeenCalledWith("compact");
  });
});
