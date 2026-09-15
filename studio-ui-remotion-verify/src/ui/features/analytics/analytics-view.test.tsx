import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AnalyticsDashboard, fallback } from "../../App";

describe("Channel portfolio workspace", () => {
  it("keeps active channel data in the workstation portfolio", () => {
    const data = { ...fallback, channels: [{ id: "channel-1", channel: "https://youtube.com/@news", name: "Новости", subscribers: "1000", status: "Подключён" }] };
    render(<AnalyticsDashboard data={data} command={vi.fn()} />);

    expect(screen.getByLabelText("Channel Portfolio Workspace")).toBeTruthy();
    expect(screen.getByRole("table", { name: "Каналы YouTube" })).toBeTruthy();
  });
});
