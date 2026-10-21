import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Covers, fallback } from "../../App";

const text = "Тема: Сад\n\nFirst\n\nSecond\n\nТема: Хлеб\n\nThird";
const preview = {
  ...fallback,
  operationResult: {
    kind: "cover-prompt-blocks-preview", count: 3, previewToken: "confirmed",
    topics: [
      { title: "Сад", productionItemId: "garden-id", variants: [{ id: "v1", number: 1, prompt: "First", added: true }, { id: "v2", number: 2, prompt: "Second", added: true }] },
      { title: "Хлеб", productionItemId: "bread-id", variants: [{ id: "v3", number: 1, prompt: "Third", added: true }] },
    ],
  },
};

describe("Manual multi-prompt blocks", () => {
  it("loads the saved checkbox after the startup snapshot arrives", () => {
    const command = vi.fn();
    const view = render(<Covers data={fallback} command={command} />);
    view.rerender(<Covers data={{ ...fallback, coverSettings: { ...fallback.coverSettings, manualMissingOnly: false } }} command={command} />);
    expect(screen.getByLabelText("Только недостающие варианты — готовые сохранить")).toHaveProperty("checked", false);
  });
  it("persists the missing-only checkbox and sends its choice to generation", async () => {
    const command = vi.fn(async () => fallback);
    render(<Covers data={{ ...fallback, covers: [{ production_item_id: "garden", title: "Сад", image_prompt: "Greenhouse", paths: [] }], coverSettings: { ...fallback.coverSettings, manualMissingOnly: true } }} command={command} />);
    const checkbox = screen.getByLabelText("Только недостающие варианты — готовые сохранить");
    expect(checkbox).toHaveProperty("checked", true);
    fireEvent.click(checkbox);
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-cover-settings", { manualMissingOnly: false }));
    fireEvent.click(screen.getByRole("button", { name: "Запустить" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("generate-covers", expect.objectContaining({ manualMissingOnly: false })));
  });
  it("previews the backend assignment then commits its token without generating", async () => {
    const command = vi.fn(async (_name, payload) => payload.previewOnly ? preview : fallback);
    render(<Covers data={{ ...fallback, covers: [] }} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Добавить несколько промптов" }));
    fireEvent.change(screen.getByLabelText("Темы и промпты"), { target: { value: text } });
    expect(screen.getByRole("button", { name: "Добавить в обложки" })).toHaveProperty("disabled", true);
    fireEvent.click(screen.getByRole("button", { name: "Проверить привязку" }));
    await screen.findByText("garden-id");
    expect(screen.getByText("bread-id")).toBeTruthy();
    expect(command).toHaveBeenCalledWith("import-cover-prompt-pairs", expect.objectContaining({ text, mode: "blocks", previewOnly: true, createMissingTopics: true }));
    const importId = command.mock.calls[0][1].importId;
    fireEvent.click(screen.getByRole("button", { name: "Добавить в обложки" }));
    await waitFor(() => expect(command).toHaveBeenCalledTimes(2));
    expect(command.mock.calls[1]).toEqual(["import-cover-prompt-pairs", { text, mode: "blocks", createMissingTopics: true, importId, previewToken: "confirmed" }]);
    expect(command.mock.calls.every(([name]) => name === "import-cover-prompt-pairs")).toBe(true);
  });

  it("invalidates the preview when text changes and preserves rejected input", async () => {
    const command = vi.fn(async (_name, payload) => payload.previewOnly ? preview : undefined);
    render(<Covers data={{ ...fallback, covers: [] }} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Добавить несколько промптов" }));
    fireEvent.change(screen.getByLabelText("Темы и промпты"), { target: { value: text } });
    fireEvent.click(screen.getByRole("button", { name: "Проверить привязку" }));
    await screen.findByText("garden-id");
    fireEvent.change(screen.getByLabelText("Темы и промпты"), { target: { value: text + "\n\nFourth" } });
    expect(screen.queryByText("garden-id")).toBeNull();
    expect(screen.getByRole("button", { name: "Добавить в обложки" })).toHaveProperty("disabled", true);
    fireEvent.click(screen.getByRole("button", { name: "Проверить привязку" }));
    await screen.findByText("garden-id");
    fireEvent.click(screen.getByRole("button", { name: "Добавить в обложки" }));
    await screen.findByRole("alert");
    expect(screen.getByLabelText("Темы и промпты")).toHaveProperty("value", text + "\n\nFourth");
  });
});
