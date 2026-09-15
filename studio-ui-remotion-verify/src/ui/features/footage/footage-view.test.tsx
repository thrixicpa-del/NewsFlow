import { render, screen } from "@testing-library/react";
import { Cutter, fallback, Footage } from "../../App";
import { describe, expect, it, vi } from "vitest";

describe("Media ingest workspaces", () => {
  it("keeps the current footage library inside a named ingest workspace", () => {
    render(<Footage data={{ ...fallback, footageFolders: ["D:/footage"] }} command={vi.fn()} refresh={async () => undefined} />);

    expect(screen.getByLabelText("Media Ingest Workspace")).toBeTruthy();
    expect(screen.getByRole("table", { name: "Источники футажей" })).toBeTruthy();
  });

  it("keeps cutter sources in the focused cutter workspace", () => {
    render(<Cutter data={fallback} command={vi.fn()} />);

    expect(screen.getByLabelText("Footage Cutter Workspace")).toBeTruthy();
    expect(screen.getByRole("table", { name: "Исходники для нарезки" })).toBeTruthy();
  });
});
