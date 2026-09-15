import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Dashboard } from "../../App";

describe("Dashboard Light view", () => {
  it("keeps the existing navigation and auto-pipeline command contract", () => {
    const go = vi.fn();
    const command = vi.fn();
    render(<Dashboard stats={[[1, "Идеи"], [2, "Сценарии"], [3, "Озвучка"], [4, "MP4"]]} target="300" setTarget={() => undefined} saveTarget={() => undefined} autoEnabled={false} autoStages={{ scenarios: true, covers: true, seo: true, voice: true, montage: true, package: true }} command={command} go={go} />);

    expect(screen.getByLabelText("Готовность Production Control Room")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /создать выпуск/i }));
    fireEvent.click(screen.getByRole("button", { name: /запустить автоэтапы/i }));
    expect(go).toHaveBeenCalledWith("ideas");
    expect(command).toHaveBeenCalledWith("run-auto-pipeline", { enabled: true, stages: { scenarios: true, covers: true, seo: true, voice: true, montage: true, package: true } });
  });
});
