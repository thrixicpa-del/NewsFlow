import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceErrorBoundary } from "./WorkspaceErrorBoundary";

function Crash(): never {
  throw new Error("cover workspace failure");
}

describe("WorkspaceErrorBoundary", () => {
  it("isolates a failed workspace and offers renderer-local recovery", () => {
    const onRetry = vi.fn();
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(
      <WorkspaceErrorBoundary workspace="Covers" onRetry={onRetry}>
        <Crash />
      </WorkspaceErrorBoundary>,
    );

    expect(screen.getByRole("alert").textContent).toContain("Рабочая область Covers временно недоступна");
    expect(screen.getByText(/Код диагностики:/).textContent).toMatch(/Covers-/);
    fireEvent.click(screen.getByRole("button", { name: "Повторить загрузку области" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    consoleError.mockRestore();
  });
});
