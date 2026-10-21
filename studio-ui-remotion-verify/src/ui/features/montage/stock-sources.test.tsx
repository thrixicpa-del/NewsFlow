import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Editor, fallback } from "../../App";

const stockSettings = {
  sourceMode: "hybrid" as const,
  stockSources: ["pexels", "pixabay", "coverr", "wikimedia", "nasa"],
  stockTrim: true,
  stockKeys: [
    { id: "key-a", provider: "pexels", label: "Pexels 1", active: true },
    { id: "key-b", provider: "pexels", label: "Pexels 2", active: false },
  ],
};
const snapshot = () => ({ ...fallback, montageSettings: { ...fallback.montageSettings, ...stockSettings } });
const openSettings = (data: NewsFlowSnapshot = snapshot(), command = vi.fn().mockResolvedValue(data)) => {
  const view = render(<Editor data={data} command={command} refresh={async () => undefined} />);
  fireEvent.click(screen.getByRole("button", { name: "Настроить монтаж" }));
  return { ...view, command };
};

describe("Montage stock source settings", () => {
  it("shows only the HD quality preference with automatic continuity described", () => {
    const data = snapshot();
    openSettings({ ...data, montageSettings: { ...data.montageSettings, stockHdOnly: undefined } });
    expect(screen.queryByRole("checkbox", { name: "Автозаполнение пропусков" })).toBeNull();
    expect((screen.getByRole("checkbox", { name: "HD 720p+" }) as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText("Если материалов не хватает, используем тематические перебивки или удерживаем кадр; озвучка продолжается.")).toBeTruthy();
  });

  it("saves the HD draft across background refresh without a continuity toggle", async () => {
    const data = snapshot();
    const { command, rerender } = openSettings(data);
    fireEvent.click(screen.getByRole("checkbox", { name: "HD 720p+" }));
    rerender(<Editor data={{ ...data, montageSettings: { ...data.montageSettings } }} command={command} refresh={async () => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Сохранить выбор" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-montage-settings", expect.objectContaining({ stockHdOnly: false })));
    expect(command.mock.calls[0][1]).not.toHaveProperty("autoFillGaps");
  });

  it("loads the saved HD preference before launching the queue", async () => {
    const base = snapshot();
    const data = { ...base, montageSettings: { ...base.montageSettings, stockHdOnly: false }, scenarios: [{ index: 1, title: "Synthetic", state: "Готово", result: "Text", error: "" }], voiceItems: [{ index: 1, title: "Synthetic", state: "Готово", path: "D:/synthetic.mp3" }] };
    const { command } = openSettings(data);
    expect((screen.getByRole("checkbox", { name: "HD 720p+" }) as HTMLInputElement).checked).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    fireEvent.click(screen.getByRole("button", { name: "Собрать незавершённые" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-montage-settings", expect.objectContaining({ stockHdOnly: false })));
    expect(command.mock.calls[0][1]).not.toHaveProperty("autoFillGaps");
    await waitFor(() => expect(command).toHaveBeenCalledWith("run-montage-queue", { indices: [1], replaceOutput: false }));
    expect(command.mock.calls.findIndex(([name]) => name === "save-montage-settings")).toBeLessThan(command.mock.calls.findIndex(([name]) => name === "run-montage-queue"));
  });

  it.each([
    { autoWeb: false, externalOnly: false, mode: "local" },
    { autoWeb: true, externalOnly: false, mode: "hybrid" },
    { autoWeb: true, externalOnly: true, mode: "stock" },
  ])("reads legacy source flags as $mode with trimming enabled by default", ({ autoWeb, externalOnly, mode }) => {
    openSettings({ ...fallback, montageSettings: { ...fallback.montageSettings, sourceMode: undefined, stockSources: undefined, stockTrim: undefined, autoWeb, externalOnly } });
    expect((screen.getByLabelText("Источники футажей") as HTMLSelectElement).value).toBe(mode);
    expect((screen.getByRole("checkbox", { name: "Обрезать стоковые видео" }) as HTMLInputElement).checked).toBe(true);
  });

  it.each(["local", "hybrid", "stock"])("saves %s source mode with the existing uniqueness settings", async (sourceMode) => {
    const { command } = openSettings();
    fireEvent.change(screen.getByLabelText("Источники футажей"), { target: { value: sourceMode } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить выбор" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-montage-settings", expect.objectContaining({
      sourceMode, stockSources: ["pexels", "pixabay", "coverr", "wikimedia", "nasa"], stockTrim: true,
      fastReuseEnabled: false, uniqueFootagePercent: 100,
      autoWeb: sourceMode !== "local", externalOnly: sourceMode === "stock",
    })));
  });

  it("shows the downloaded library path and saves its opt-out", async () => {
    const data = snapshot();
    const folder = "D:/Test stocks/Стоки";
    const { command } = openSettings({ ...data, montageSettings: { ...data.montageSettings, stockLibraryFolder: folder } });
    const checkbox = screen.getByRole("checkbox", { name: "Использовать библиотеку скачанных стоков" });
    expect((checkbox as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText(folder)).toBeTruthy();
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: "Сохранить выбор" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-montage-settings", expect.objectContaining({ stockUseLibrary: false })));
  });

  it("accepts a manually entered download worker count above eight without a maximum", async () => {
    const { command } = openSettings();
    const input = screen.getByLabelText("Одновременные скачивания") as HTMLInputElement;
    expect(input.max).toBe("");
    fireEvent.change(input, { target: { value: "64" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить выбор" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-montage-settings", expect.objectContaining({ downloadWorkers: 64 })));
  });

  it("offers an explicit local plus stocks checkbox bound to the existing source mode", async () => {
    const { command } = openSettings({ ...snapshot(), montageSettings: { ...snapshot().montageSettings, sourceMode: "local" } });
    const toggle = screen.getByRole("checkbox", { name: "Использовать стоки с моими футажами" });
    expect((toggle as HTMLInputElement).checked).toBe(false);
    fireEvent.click(toggle);
    expect((screen.getByLabelText("Источники футажей") as HTMLSelectElement).value).toBe("hybrid");
    fireEvent.click(screen.getByRole("button", { name: "Сохранить выбор" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-montage-settings", expect.objectContaining({ sourceMode: "hybrid", autoWeb: true, externalOnly: false })));
    fireEvent.click(toggle);
    expect((screen.getByLabelText("Источники футажей") as HTMLSelectElement).value).toBe("local");
  });

  it("selects all providers visibly and allows removing just one afterwards", async () => {
    const { command } = openSettings();
    fireEvent.click(screen.getByRole("checkbox", { name: "Все вместе" }));
    expect((screen.getByRole("checkbox", { name: "Pexels" }) as HTMLInputElement).checked).toBe(false);
    expect((screen.getByRole("button", { name: "Сохранить выбор" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("checkbox", { name: "Все вместе" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Pexels" }));
    expect((screen.getByRole("checkbox", { name: "Все вместе" }) as HTMLInputElement).checked).toBe(false);
    fireEvent.click(screen.getByRole("checkbox", { name: "Обрезать стоковые видео" }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить выбор" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-montage-settings", expect.objectContaining({
      stockSources: ["pixabay", "coverr", "wikimedia", "nasa"], stockTrim: false,
    })));
  });

  it("keeps source drafts across background refresh", async () => {
    const data = { ...snapshot(), scenarios: [{ index: 1, title: "Synthetic", state: "Готово", result: "Text", error: "" }], voiceItems: [{ index: 1, title: "Synthetic", state: "Готово", path: "D:/synthetic.mp3" }] };
    const { command, rerender } = openSettings(data);
    fireEvent.change(screen.getByLabelText("Источники футажей"), { target: { value: "stock" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "NASA" }));
    rerender(<Editor data={{ ...data, montageSettings: { ...data.montageSettings } }} command={command} refresh={async () => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Сохранить выбор" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-montage-settings", expect.objectContaining({ sourceMode: "stock", stockSources: ["pexels", "pixabay", "coverr", "wikimedia"] })));
  });

  it("sends saved source settings before starting the queue", async () => {
    const data = { ...snapshot(), scenarios: [{ index: 1, title: "Synthetic", state: "Готово", result: "Text", error: "" }], voiceItems: [{ index: 1, title: "Synthetic", state: "Готово", path: "D:/synthetic.mp3" }] };
    const command = vi.fn().mockResolvedValue(data);
    render(<Editor data={data} command={command} refresh={async () => undefined} />);
    fireEvent.click(screen.getByRole("button", { name: "Собрать незавершённые" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-montage-settings", expect.objectContaining({ sourceMode: "hybrid", stockSources: ["pexels", "pixabay", "coverr", "wikimedia", "nasa"], stockTrim: true })));
    await waitFor(() => expect(command).toHaveBeenCalledWith("run-montage-queue", { indices: [1], replaceOutput: false }));
  });

  it("adds multiple keys for the selected provider and clears only after success", async () => {
    const { command } = openSettings();
    const input = screen.getByLabelText("Новые API-ключи стоков") as HTMLTextAreaElement;
    expect((input.style as CSSStyleDeclaration & { WebkitTextSecurity: string }).WebkitTextSecurity).toBe("disc");
    fireEvent.change(screen.getByLabelText("Провайдер API-ключей"), { target: { value: "pixabay" } });
    fireEvent.change(input, { target: { value: "synthetic-one\n\n synthetic-two " } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить ключи" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-montage-stock-keys", { provider: "pixabay", keys: ["synthetic-one", "synthetic-two"] }));
    await waitFor(() => expect(input.value).toBe(""));
    expect(screen.getByText("Pexels: активно 1 из 2")).toBeTruthy();
  });

  it("retains a failed key draft and allows a safe retry", async () => {
    const command = vi.fn().mockResolvedValue(null);
    openSettings(snapshot(), command);
    const input = screen.getByLabelText("Новые API-ключи стоков") as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "synthetic-retry" } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить ключи" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Не удалось сохранить ключи"));
    expect(input.value).toBe("synthetic-retry");
    expect(screen.queryByText("synthetic-retry", { selector: ":not(textarea)" })).toBeNull();
  });

  it("discards unsaved secrets when closing settings", async () => {
    const { command } = openSettings();
    fireEvent.change(screen.getByLabelText("Новые API-ключи стоков"), { target: { value: "synthetic-not-saved" } });
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    fireEvent.click(screen.getByRole("button", { name: "Настроить монтаж" }));
    expect((screen.getByLabelText("Новые API-ключи стоков") as HTMLTextAreaElement).value).toBe("");
    expect(command).not.toHaveBeenCalled();
  });

  it("uses stable ids to enable and remove safe key rows", async () => {
    const { command } = openSettings();
    fireEvent.click(screen.getByRole("checkbox", { name: "Активен Pexels 2" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-montage-stock-keys", { id: "key-b", active: true }));
    fireEvent.click(screen.getByRole("button", { name: "Удалить Pexels 1" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-montage-stock-keys", { id: "key-a", remove: true }));
  });
});
