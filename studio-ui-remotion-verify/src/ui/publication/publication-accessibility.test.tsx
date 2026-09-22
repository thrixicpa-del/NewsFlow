import "@testing-library/jest-dom/vitest";
import axe from "axe-core";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { fallback } from "../App";
import { buildVisualFixture } from "../visual-regression/visual-fixtures";
import { PublicationPage } from "./PublicationPage";

const fixture = buildVisualFixture(fallback, "publication-84") as NewsFlowSnapshot;

describe("Publication V2 accessibility", () => {
  it("has no serious or critical axe violations on the bulk workspace", async () => {
    const view = render(<PublicationPage data={fixture} command={vi.fn().mockResolvedValue(undefined)} />);
    const result = await axe.run(view.container, {
      rules: {
        "color-contrast": { enabled: false },
      },
    });
    const blocking = result.violations.filter((violation) => ["serious", "critical"].includes(String(violation.impact)));
    expect(blocking.map((violation) => ({ id: violation.id, nodes: violation.nodes.map((node) => node.target) }))).toEqual([]);
  });

  it("keeps bulk controls reachable by accessible names and native controls", () => {
    render(<PublicationPage data={fixture} command={vi.fn().mockResolvedValue(undefined)} />);

    expect(screen.getByRole("tab", { name: "Ролики" })).toBeInTheDocument();
    expect(screen.getByLabelText("Выбрать все ролики")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Каналы" }));
    fireEvent.click(screen.getByRole("button", { name: "Действия канала Канал 1" }));

    expect(screen.getByLabelText("Первый выход канала")).toHaveAttribute("step", "900");
    expect(screen.getByLabelText("Окно публикации: начало")).toHaveAttribute("step", "900");
    expect(screen.getByRole("button", { name: "Сохранить" })).toBeEnabled();
  });

  it("exposes queue selection and ads status without mouse-only actions", () => {
    render(<PublicationPage data={fixture} command={vi.fn().mockResolvedValue(undefined)} />);
    fireEvent.click(screen.getByRole("tab", { name: "Очередь" }));

    expect(screen.getByLabelText("Выбрать всю очередь")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Реклама" })).toBeInTheDocument();
    expect(screen.getAllByText("AUTO + MANUAL 39s").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Запустить очередь" })).toBeEnabled();
  });
});
