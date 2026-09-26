import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Outputs, fallback } from "../../App";

describe("Results batch export", () => {
  afterEach(() => {
    window.newsflowDesktop = undefined;
  });

  it("persists a chosen Results destination, exports the batch, and opens the runtime path", async () => {
    const chooseFolder = vi.fn().mockResolvedValue("D:/Exports");
    const openPath = vi.fn().mockResolvedValue("");
    window.newsflowDesktop = { chooseFolder, openPath } as unknown as typeof window.newsflowDesktop;
    const data = {
      ...fallback,
      results: { outputFolder: "D:/Exports", lastExportFolder: "" },
    } as NewsFlowSnapshot;
    const command = vi.fn().mockResolvedValue(data);

    render(<Outputs data={data} command={command} />);

    expect(screen.getByLabelText("Папка Results").textContent).toContain("D:/Exports");
    fireEvent.click(screen.getByRole("button", { name: "Выбрать папку" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "save-settings", { resultsOutputFolder: "D:/Exports" },
    ));
    fireEvent.click(screen.getByRole("button", { name: "Собрать результаты" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("export-results-batch"));
    fireEvent.click(screen.getByRole("button", { name: "Открыть папку" }));
    expect(openPath).toHaveBeenCalledWith("D:/Exports");
  });

  it("opens the last created batch before the selected destination", () => {
    const openPath = vi.fn().mockResolvedValue("");
    window.newsflowDesktop = { openPath } as unknown as typeof window.newsflowDesktop;
    const data = {
      ...fallback,
      results: { outputFolder: "D:/Exports", lastExportFolder: "D:/Exports/NewsFlow Results — 2026-09-23 11-30-00" },
    } as NewsFlowSnapshot;

    render(<Outputs data={data} command={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Открыть папку" }));

    expect(openPath).toHaveBeenCalledWith("D:/Exports/NewsFlow Results — 2026-09-23 11-30-00");
  });

  it("keeps manual export in one batch instead of offering per-video publication packages", () => {
    const data = {
      ...fallback,
      results: { outputFolder: "D:/Exports", lastExportFolder: "" },
    } as NewsFlowSnapshot;

    render(<Outputs data={data} command={vi.fn()} />);

    expect(screen.getByText("Три согласованных TXT, выбранные обложки и готовые MP4 без изменения Publication-пакетов.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Собрать пакеты для публикации" })).not.toBeInTheDocument();
  });
});
