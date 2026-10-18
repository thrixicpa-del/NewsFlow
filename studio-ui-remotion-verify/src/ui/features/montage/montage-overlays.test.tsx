import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Editor, fallback } from "../../App";

const layer = {
  id: "logo", name: "Logo", enabled: true, path: "D:/synthetic/logo #1.png", kind: "image" as const,
  x: 20, y: 30, width: 400, height: 200, keepAspect: true, opacity: 1,
  start: 0, duration: 5, mode: "once" as const, repeatEvery: 10, endOffset: 5,
  chromaEnabled: false, chromaColor: "#00FF00", chromaSimilarity: 0.1, chromaBlend: 0.05, audioEnabled: false,
};
const template = { version: 1 as const, layouts: { "16:9": [layer], "9:16": [] } };
function setup(extra: Partial<NewsFlowSnapshot> = {}) {
  const data = { ...fallback, montageSettings: { ...fallback.montageSettings, overlayTemplate: template }, ...extra };
  const command = vi.fn().mockResolvedValue(data);
  const view = render(<Editor data={data} command={command} refresh={async () => undefined} />);
  fireEvent.click(screen.getByRole("button", { name: "Наложения" }));
  return { command, data, ...view };
}
afterEach(() => { delete window.newsflowDesktop; vi.useRealTimers(); });

describe("inline montage overlays", () => {
  it("preserves unfinished edits when another interval is removed and reindexes later drafts", () => {
    setup();
    fireEvent.change(screen.getByLabelText("Режим показа"), { target: { value: "intervals" } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить интервал" }));
    fireEvent.click(screen.getByRole("button", { name: "Добавить интервал" }));
    fireEvent.change(screen.getByLabelText("Интервал 1: начало, с"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Интервал 3: конец, с"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Удалить интервал 2" }));
    expect(screen.getByLabelText("Интервал 1: начало, с")).toHaveProperty("value", "");
    expect(screen.getByLabelText("Интервал 2: конец, с")).toHaveProperty("value", "");
    expect(screen.getByRole("button", { name: "Сохранить для новых" })).toHaveProperty("disabled", true);
  });
  it("keeps timing independent for different files and clears hidden invalid end drafts", () => {
    setup({ montageSettings: { ...fallback.montageSettings, overlayTemplate: { ...template, layouts: { "16:9": [layer, { ...layer, id: "card", name: "Card" }], "9:16": [] } } } });
    fireEvent.change(screen.getByLabelText("Режим показа"), { target: { value: "intervals" } });
    fireEvent.change(screen.getByLabelText("Интервал 1: начало, с"), { target: { value: "6" } });
    fireEvent.change(screen.getByLabelText("Интервал 1: конец, с"), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "Card" }));
    expect((screen.getByLabelText("Режим показа") as HTMLSelectElement).value).toBe("once");
    fireEvent.change(screen.getByLabelText("Режим показа"), { target: { value: "count" } });
    fireEvent.click(screen.getByLabelText("Диапазон до конца MP4"));
    fireEvent.change(screen.getByLabelText("Конец диапазона, с"), { target: { value: "" } });
    expect(screen.getByRole("button", { name: "Сохранить для новых" })).toHaveProperty("disabled", true);
    fireEvent.click(screen.getByLabelText("Диапазон до конца MP4"));
    expect(screen.getByRole("button", { name: "Сохранить для новых" })).toHaveProperty("disabled", false);
    fireEvent.change(screen.getByLabelText("Количество показов"), { target: { value: "0" } });
    fireEvent.change(screen.getByLabelText("Режим показа"), { target: { value: "until-end" } });
    expect(screen.getByRole("button", { name: "Сохранить для новых" })).toHaveProperty("disabled", false);
    fireEvent.click(screen.getByRole("button", { name: "Logo" }));
    expect((screen.getByLabelText("Интервал 1: конец, с") as HTMLInputElement).value).toBe("12");
  });
  it("edits separate explicit ranges for each layer and saves them in the template", async () => {
    const { command } = setup();
    fireEvent.change(screen.getByLabelText("Режим показа"), { target: { value: "intervals" } });
    expect(screen.getByRole("group", { name: "Когда показывать: Logo" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Интервал 1: начало, с"), { target: { value: "6" } });
    fireEvent.change(screen.getByLabelText("Интервал 1: конец, с"), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить интервал" }));
    fireEvent.change(screen.getByLabelText("Интервал 2: начало, с"), { target: { value: "80" } });
    fireEvent.change(screen.getByLabelText("Интервал 2: конец, с"), { target: { value: "88" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить для новых" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-montage-overlays", expect.objectContaining({ template: expect.objectContaining({ layouts: { "16:9": [expect.objectContaining({ mode: "intervals", ranges: [{ start: 6, end: 12 }, { start: 80, end: 88 }] })], "9:16": [] } }) })));
  });
  it("distributes a requested number over a bounded window or through the MP4 end", async () => {
    const { command } = setup();
    fireEvent.change(screen.getByLabelText("Режим показа"), { target: { value: "count" } });
    fireEvent.change(screen.getByLabelText("Начало, с"), { target: { value: "6" } });
    fireEvent.change(screen.getByLabelText("Длительность, с"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Количество показов"), { target: { value: "4" } });
    expect((screen.getByLabelText("Диапазон до конца MP4") as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByLabelText("Диапазон до конца MP4"));
    fireEvent.change(screen.getByLabelText("Конец диапазона, с"), { target: { value: "12" } });
    expect(screen.getByRole("button", { name: "Сохранить для новых" })).toHaveProperty("disabled", true);
    fireEvent.change(screen.getByLabelText("Конец диапазона, с"), { target: { value: "32" } });
    fireEvent.change(screen.getByLabelText("Позиция предпросмотра, с"), { target: { value: "15" } });
    expect(screen.getByLabelText("Слой предпросмотра Logo")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Позиция предпросмотра, с"), { target: { value: "17" } });
    expect(screen.queryByLabelText("Слой предпросмотра Logo")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Сохранить для новых" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-montage-overlays", expect.objectContaining({ template: expect.objectContaining({ layouts: { "16:9": [expect.objectContaining({ mode: "count", start: 6, duration: 2, repeatCount: 4, rangeEnd: 32 })], "9:16": [] } }) })));
  });
  it("updates geometry immediately, preserves ratio and keeps layouts independent", () => {
    setup();
    fireEvent.change(screen.getByLabelText("Ширина, px"), { target: { value: "600" } });
    expect((screen.getByLabelText("Высота, px") as HTMLInputElement).value).toBe("300");
    expect(screen.getByLabelText("Слой предпросмотра Logo").style.width).toBe("31.25%");
    fireEvent.change(screen.getByLabelText("X, px"), { target: { value: "70" } });
    fireEvent.click(screen.getByRole("button", { name: "9:16" }));
    expect(screen.queryByLabelText("X, px")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "16:9" }));
    expect((screen.getByLabelText("X, px") as HTMLInputElement).value).toBe("70");
  });
  it("adds multiple local files with silent video and safely encodes preview paths", async () => {
    window.newsflowDesktop = { chooseImages: vi.fn().mockResolvedValue(["D:/synthetic/a.png", "D:/synthetic/b.jpg"]), chooseVideos: vi.fn().mockResolvedValue(["D:/synthetic/clip.mp4"]) } as unknown as Window["newsflowDesktop"];
    const { command } = setup();
    expect(screen.getByAltText("Logo").getAttribute("src")).toBe("file:///D:/synthetic/logo%20%231.png");
    fireEvent.click(screen.getByRole("button", { name: "Добавить изображения" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "b.jpg" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Добавить видео" }));
    await waitFor(() => expect(screen.getByLabelText("Звук слоя")).toBeTruthy());
    expect((screen.getByLabelText("Звук слоя") as HTMLInputElement).checked).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Сохранить для новых" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-montage-overlays", expect.objectContaining({ scope: "new", indices: [], overwrite: false, template: expect.objectContaining({ layouts: { "16:9": expect.arrayContaining([expect.objectContaining({ kind: "video", audioEnabled: false })]), "9:16": [] } }) })));
  });
  it("applies selected queue indices only after explicit individualized overwrite confirmation", async () => {
    const { command } = setup({
      scenarios: [{ index: 2, title: "Synthetic selected", state: "Готово", result: "Text", error: "" }],
      voiceItems: [{ index: 2, title: "Synthetic selected", state: "Готово", path: "D:/synthetic/voice.mp3" }],
      montageTasks: [{ index: 2, title: "Synthetic selected", status: "Готов к монтажу", overlayTemplateIndividualized: true }],
    });
    fireEvent.click(screen.getByRole("button", { name: /Synthetic selected/ }));
    fireEvent.click(screen.getByRole("button", { name: "Применить к выбранным (1)" }));
    expect(command).not.toHaveBeenCalled();
    const confirmation = screen.getByRole("group", { name: "Замена индивидуальных наложений" });
    fireEvent.click(within(confirmation).getByRole("button", { name: "Заменить индивидуальные" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-montage-overlays", { template, scope: "selected", indices: [2], overwrite: true }));
  });
  it("keeps unsaved drafts on background refresh and handles backend failure visibly", async () => {
    const { command, data, rerender } = setup();
    fireEvent.change(screen.getByLabelText("X, px"), { target: { value: "123" } });
    rerender(<Editor data={{ ...data, montageSettings: { ...data.montageSettings } }} command={command} refresh={async () => undefined} />);
    expect((screen.getByLabelText("X, px") as HTMLInputElement).value).toBe("123");
    command.mockRejectedValueOnce(new Error("Synthetic missing overlay file"));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить для новых" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Synthetic missing overlay file"));
  });
  it("previews timing including intro and never displays raw green when chromakey is enabled", () => {
    setup();
    fireEvent.change(screen.getByLabelText("Режим показа"), { target: { value: "repeat" } });
    fireEvent.change(screen.getByLabelText("Начало, с"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Повтор каждые, с"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText("Позиция предпросмотра, с"), { target: { value: "8" } });
    expect(screen.queryByLabelText("Слой предпросмотра Logo")).toBeNull();
    fireEvent.change(screen.getByLabelText("Позиция предпросмотра, с"), { target: { value: "12" } });
    expect(screen.getByLabelText("Слой предпросмотра Logo")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Хромакей"));
    expect(screen.queryByAltText("Logo")).toBeNull();
    expect(screen.getByLabelText("Хромакей Logo").tagName).toBe("CANVAS");
  });
  it("keeps invalid empty numeric drafts and blocks saving instead of coercing to zero", () => {
    const { command } = setup();
    fireEvent.change(screen.getByLabelText("Ширина, px"), { target: { value: "" } });
    expect((screen.getByLabelText("Ширина, px") as HTMLInputElement).value).toBe("");
    expect((screen.getByRole("button", { name: "Сохранить для новых" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Сохранить для новых" }));
    expect(command).not.toHaveBeenCalled();
  });
  it("rejects remote sources without loading them", () => {
    setup({ montageSettings: { ...fallback.montageSettings, overlayTemplate: { version: 1, layouts: { "16:9": [{ ...layer, path: "https://example.test/logo.png" }], "9:16": [] } } } });
    expect(screen.queryByAltText("Logo")).toBeNull();
    expect(screen.getByRole("alert").textContent).toContain("локальный");
  });
  it("resets a clipped end insertion to source zero", () => {
    setup({ montageSettings: { ...fallback.montageSettings, overlayTemplate: { version: 1, layouts: { "16:9": [{ ...layer, name: "End clip", kind: "video", path: "D:/synthetic/end.mp4", mode: "end", endOffset: 12, duration: 5 }], "9:16": [] } } } });
    fireEvent.change(screen.getByLabelText("Полная длина с заставкой, с"), { target: { value: "10" } });
    const video = screen.getByLabelText("End clip") as HTMLVideoElement;
    fireEvent.loadedMetadata(video);
    expect(video.currentTime).toBe(0);
    fireEvent.change(screen.getByLabelText("Позиция предпросмотра, с"), { target: { value: "3" } });
    expect(screen.queryByLabelText("Слой предпросмотра End clip")).toBeNull();
  });
  it("rejects unsupported image types returned by the shared picker", async () => {
    window.newsflowDesktop = { chooseImages: vi.fn().mockResolvedValue(["D:/synthetic/unsupported.webp"]) } as unknown as Window["newsflowDesktop"];
    setup();
    fireEvent.click(screen.getByRole("button", { name: "Добавить изображения" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("PNG или JPG"));
    expect(screen.queryByRole("button", { name: "unsupported.webp" })).toBeNull();
  });
  it("locks the draft during an in-flight save so late success cannot discard newer edits", async () => {
    const { command, data } = setup();
    let finish!: (value: NewsFlowSnapshot) => void;
    command.mockReturnValueOnce(new Promise<NewsFlowSnapshot>((resolve) => { finish = resolve; }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить для новых" }));
    expect(screen.getByLabelText("X, px").matches(":disabled")).toBe(true);
    finish(data);
    await waitFor(() => expect(screen.getByLabelText("X, px").matches(":disabled")).toBe(false));
  });
  it("requires confirmation for selected saved projects even when the queue has no individualized flag", async () => {
    const { command } = setup({
      scenarios: [{ index: 4, title: "Unflagged project", state: "Готово", result: "Text", error: "" }],
      voiceItems: [{ index: 4, title: "Unflagged project", state: "Готово", path: "D:/synthetic/voice.mp3" }],
      montageTasks: [{ index: 4, title: "Unflagged project", status: "Готов к монтажу", projectPath: "D:/synthetic/project.json" }],
    });
    fireEvent.click(screen.getByRole("button", { name: /Unflagged project/ }));
    fireEvent.click(screen.getByRole("button", { name: "Применить к выбранным (1)" }));
    expect(command).not.toHaveBeenCalled();
    const confirmation = screen.getByRole("group", { name: "Замена индивидуальных наложений" });
    fireEvent.click(within(confirmation).getByRole("button", { name: "Заменить индивидуальные" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-montage-overlays", { template, scope: "selected", indices: [4], overwrite: true }));
  });
  it("shows a manual preparation warning when XML must wait for a flattened overlay render", () => {
    render(<Editor data={{ ...fallback, preparedProject: { title: "Synthetic", path: "D:/synthetic/project.json", clips: 1, duration: 10, warning: "DaVinci XML с наложениями будет создан после рендера" } }} command={vi.fn()} refresh={async () => undefined} />);
    expect(screen.getByRole("alert").textContent).toContain("DaVinci XML с наложениями будет создан после рендера");
  });
  it("applies to the whole unique scenario/task queue, including rows without MP3, after confirmation", async () => {
    const { command } = setup({
      scenarios: [
        { index: 2, title: "Selected row", state: "Готово", result: "Text", error: "" },
        { index: 7, title: "No MP3 yet", state: "Готово", result: "Text", error: "" },
        { index: -1, title: "Invalid legacy row", state: "", result: "", error: "" },
      ],
      voiceItems: [{ index: 2, title: "Selected row", state: "Готово", path: "D:/synthetic/voice.mp3" }],
      montageTasks: [
        { index: 2, title: "Selected row", status: "Готов к монтажу" },
        { index: 9, title: "Task only", status: "Рендер" },
      ],
    });
    fireEvent.click(screen.getByRole("button", { name: /Selected row/ }));
    fireEvent.click(screen.getByRole("button", { name: "Применить ко всей очереди (3)" }));
    expect(command).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole("group", { name: "Замена индивидуальных наложений" })).getByRole("button", { name: "Заменить индивидуальные" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-montage-overlays", { template, scope: "selected", indices: [2, 7, 9], overwrite: true }));
  });
  it("treats zero changed existing rows as a successful save of future defaults", async () => {
    const { command, data } = setup();
    command.mockResolvedValueOnce({ ...data, operationResult: { kind: "montage-overlays", count: 0 } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить для новых" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Шаблон сохранён для новых задач"));
    expect(screen.queryByRole("alert")).toBeNull();
  });
  it("contains a saved source inside an aspect-locked box instead of stretching it", () => {
    setup({ montageSettings: { ...fallback.montageSettings, overlayTemplate: { version: 1, layouts: { "16:9": [{ ...layer, width: 500, height: 300 }], "9:16": [] } } } });
    const image = screen.getByAltText("Logo");
    expect(image.style.objectFit).toBe("contain");
    expect(image.style.objectPosition).toBe("left top");
    fireEvent.click(screen.getByLabelText("Сохранять пропорции"));
    expect(image.style.objectFit).toBe("fill");
  });
  it("exports overlays from the saved plan without invoking preparation or normal montage settings", async () => {
    const { command } = setup({
      scenarios: [{ index: 3, title: "Saved montage", state: "Готово", result: "Text", error: "" }],
      voiceItems: [{ index: 3, title: "Saved montage", state: "Готово", path: "D:/synthetic/voice.mp3" }],
      montageTasks: [{ index: 3, title: "Saved montage", status: "Готово", projectPath: "D:/synthetic/project.json" }],
    });
    fireEvent.click(screen.getByRole("button", { name: /Saved montage/ }));
    fireEvent.click(screen.getByRole("button", { name: "Экспортировать наложения без подбора" }));
    await waitFor(() => expect(command).toHaveBeenCalledExactlyOnceWith("run-montage-queue", { indices: [3], renderOnly: true }));
  });
  it("does not offer plan-only export when a selected row has no saved project", () => {
    setup({
      scenarios: [{ index: 3, title: "No plan", state: "Готово", result: "Text", error: "" }],
      voiceItems: [{ index: 3, title: "No plan", state: "Готово", path: "D:/synthetic/voice.mp3" }],
      montageTasks: [{ index: 3, title: "No plan", status: "Готов к монтажу" }],
    });
    fireEvent.click(screen.getByRole("button", { name: /No plan/ }));
    expect((screen.getByRole("button", { name: "Экспортировать наложения без подбора" }) as HTMLButtonElement).disabled).toBe(true);
  });
  it("loads individual settings after confirming draft discard and retains them on refresh", () => {
    const individual = { version: 1 as const, layouts: { "16:9": [{ ...layer, x: 88 }], "9:16": [] } };
    const { command, data, rerender } = setup({
      scenarios: [{ index: 3, title: "Individual montage", state: "Готово", result: "Text", error: "" }],
      voiceItems: [{ index: 3, title: "Individual montage", state: "Готово", path: "D:/synthetic/voice.mp3" }],
      montageTasks: [{ index: 3, title: "Individual montage", status: "Готово", projectPath: "D:/synthetic/project.json", overlayTemplate: individual }],
    });
    fireEvent.click(screen.getByRole("button", { name: /Individual montage/ }));
    fireEvent.change(screen.getByLabelText("X, px"), { target: { value: "123" } });
    fireEvent.click(screen.getByRole("button", { name: "Загрузить настройки выбранного ролика" }));
    expect((screen.getByLabelText("X, px") as HTMLInputElement).value).toBe("123");
    fireEvent.click(screen.getByRole("button", { name: "Загрузить и отменить изменения" }));
    expect((screen.getByLabelText("X, px") as HTMLInputElement).value).toBe("88");
    rerender(<Editor data={{ ...data, montageSettings: { ...data.montageSettings } }} command={command} refresh={async () => undefined} />);
    expect((screen.getByLabelText("X, px") as HTMLInputElement).value).toBe("88");
    expect(command).not.toHaveBeenCalled();
  });
  it("explains flattened DaVinci overlays persistently when XML is enabled", () => {
    setup({ montageSettings: { ...fallback.montageSettings, exportDaVinciXml: true, overlayTemplate: template } });
    expect(screen.getByText("DaVinci XML содержит сведённый MP4 с наложениями; слои отдельно не редактируются.")).toBeTruthy();
  });
  it("loops a short video source within a longer occurrence", () => {
    setup({ montageSettings: { ...fallback.montageSettings, overlayTemplate: { version: 1, layouts: { "16:9": [{ ...layer, name: "Short clip", kind: "video", path: "D:/synthetic/short.mp4", duration: 5 }], "9:16": [] } } } });
    const video = screen.getByLabelText("Short clip") as HTMLVideoElement;
    Object.defineProperty(video, "duration", { configurable: true, value: 1 });
    fireEvent.loadedMetadata(video);
    fireEvent.change(screen.getByLabelText("Позиция предпросмотра, с"), { target: { value: "2.2" } });
    expect(video.currentTime).toBeCloseTo(0.2);
  });
  it("keeps all forty images and one video together in their chosen stack order", async () => {
    const imagePaths = Array.from({ length: 40 }, (_, index) => `D:/synthetic/image-${index + 1}.png`);
    const videoPath = "D:/synthetic/simultaneous.mp4";
    window.newsflowDesktop = { chooseImages: vi.fn().mockResolvedValue(imagePaths), chooseVideos: vi.fn().mockResolvedValue([videoPath]) } as unknown as Window["newsflowDesktop"];
    const { command } = setup({ montageSettings: { ...fallback.montageSettings, overlayTemplate: { version: 1, layouts: { "16:9": [], "9:16": [] } } } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить изображения" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "image-40.png" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Добавить видео" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "simultaneous.mp4" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Сохранить для новых" }));
    await waitFor(() => expect(command).toHaveBeenCalledTimes(1));
    const saved = command.mock.calls[0][1].template.layouts["16:9"];
    expect(saved).toHaveLength(41);
    expect(saved.map((item: { path: string }) => item.path)).toEqual([...imagePaths, videoPath]);
    expect(saved.slice(0, 40).every((item: { kind: string }) => item.kind === "image")).toBe(true);
    expect(saved[40]).toMatchObject({ kind: "video", enabled: true, audioEnabled: false });
  });
  it.each(["Готово", "Ошибка"])("keeps refreshing an overlay export until the selected card visibly reaches %s even after its worker exits", async (terminal) => {
    vi.useFakeTimers();
    const initial: NewsFlowSnapshot = {
      ...fallback,
      montageSettings: { ...fallback.montageSettings, renderer: "ffmpeg", queueRunning: false, overlayTemplate: template },
      scenarios: [{ index: 3, title: "Deferred overlay export", state: "Готово", result: "Text", error: "" }],
      voiceItems: [{ index: 3, title: "Deferred overlay export", state: "Готово", path: "D:/synthetic/voice.mp3" }],
      montageTasks: [{ index: 3, title: "Deferred overlay export", status: "Готово", projectPath: "D:/synthetic/project.json", progress: 100 }],
    };
    const stale: NewsFlowSnapshot = { ...initial, montageTasks: [{ ...initial.montageTasks[0], status: "Рендер", phase: "Подготовка рендера", progress: 60 }] };
    let reads = 0;
    const refresh = async () => {
      reads += 1;
      if (reads >= 4) view.rerender(editor({ ...stale, montageTasks: [{ ...stale.montageTasks[0], status: terminal, progress: terminal === "Готово" ? 100 : 60, ...(terminal === "Готово" ? { outputPath: "D:/synthetic/final.mp4" } : { error: "Synthetic controlled failure" }) }] }));
    };
    const command = vi.fn(async () => { view.rerender(editor(stale)); return stale; });
    const editor = (data: NewsFlowSnapshot) => <Editor data={data} command={command} refresh={refresh} />;
    const view = render(editor(initial));
    fireEvent.click(screen.getByRole("button", { name: "Наложения" }));
    fireEvent.click(screen.getByRole("button", { name: /Deferred overlay export/ }));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Экспортировать наложения без подбора" })); });
    expect(view.container.querySelector(".montage-task")?.textContent).toContain("Подготовка рендера");
    await act(async () => { await vi.advanceTimersByTimeAsync(4500); });
    const card = view.container.querySelector(terminal === "Готово" ? ".montage-task.done" : ".montage-task.error");
    expect(card?.textContent).toContain(terminal);
    const finishedReads = reads;
    await act(async () => { await vi.advanceTimersByTimeAsync(4500); });
    expect(reads).toBe(finishedReads);
    expect(command).toHaveBeenCalledExactlyOnceWith("run-montage-queue", { indices: [3], renderOnly: true });
  });
  it.each([true, false])("ignores a cloned old Ready snapshot before the new export attempt (active phase: %s)", async (hasActivePhase) => {
    vi.useFakeTimers();
    const initial: NewsFlowSnapshot = {
      ...fallback,
      montageSettings: { ...fallback.montageSettings, renderer: "ffmpeg", queueRunning: false, overlayTemplate: template },
      scenarios: [{ index: 3, title: "Semantic export watch", state: "Готово", result: "Text", error: "" }],
      voiceItems: [{ index: 3, title: "Semantic export watch", state: "Готово", path: "D:/synthetic/voice.mp3" }],
      montageTasks: [{ index: 3, title: "Semantic export watch", status: "Готово", projectPath: "D:/synthetic/project.json", updatedAt: "2026-10-18T10:00:00Z", progress: 100 }],
    };
    const cloneOld = () => ({ ...initial, montageTasks: initial.montageTasks.map((task) => ({ ...task })) });
    let reads = 0;
    const terminal = hasActivePhase ? "Готово" : "Ошибка";
    const refresh = async () => {
      reads += 1;
      const next = cloneOld();
      if (reads >= (hasActivePhase ? 4 : 3)) next.montageTasks[0] = { ...next.montageTasks[0], status: terminal, updatedAt: "2026-10-18T10:00:02Z", error: hasActivePhase ? "" : "Saved plan preflight failed" };
      else if (reads === 3 && hasActivePhase) next.montageTasks[0] = { ...next.montageTasks[0], status: "Рендер", phase: "Подготовка рендера", progress: 60 };
      view.rerender(editor(next));
    };
    const command = vi.fn(async () => { const cloned = cloneOld(); view.rerender(editor(cloned)); return cloned; });
    const editor = (data: NewsFlowSnapshot) => <Editor data={data} command={command} refresh={refresh} />;
    const view = render(editor(initial));
    fireEvent.click(screen.getByRole("button", { name: "Наложения" }));
    fireEvent.click(screen.getByRole("button", { name: /Semantic export watch/ }));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Экспортировать наложения без подбора" })); });
    expect((screen.getByRole("button", { name: "Экспортировать наложения без подбора" }) as HTMLButtonElement).disabled).toBe(true);
    await act(async () => { await vi.advanceTimersByTimeAsync(900); });
    if (hasActivePhase) expect(view.container.querySelector(".montage-task")?.textContent).toContain("Подготовка рендера");
    await act(async () => { await vi.advanceTimersByTimeAsync(1800); });
    expect(view.container.querySelector(terminal === "Готово" ? ".montage-task.done" : ".montage-task.error")?.textContent).toContain(hasActivePhase ? "Готово" : "Saved plan preflight failed");
    expect((screen.getByRole("button", { name: "Экспортировать наложения без подбора" }) as HTMLButtonElement).disabled).toBe(false);
    const stoppedAt = reads;
    await act(async () => { await vi.advanceTimersByTimeAsync(2700); });
    expect(reads).toBe(stoppedAt);
  });
  it("shows an insertion from second six until the final frame and preserves manual duration when switching back", async () => {
    const { command } = setup();
    fireEvent.change(screen.getByLabelText("Режим показа"), { target: { value: "until-end" } });
    fireEvent.change(screen.getByLabelText("Начало, с"), { target: { value: "6" } });
    expect(screen.queryByLabelText("Длительность, с")).toBeNull();
    fireEvent.change(screen.getByLabelText("Позиция предпросмотра, с"), { target: { value: "5" } });
    expect(screen.queryByLabelText("Слой предпросмотра Logo")).toBeNull();
    fireEvent.change(screen.getByLabelText("Позиция предпросмотра, с"), { target: { value: "6" } });
    expect(screen.getByLabelText("Слой предпросмотра Logo")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Позиция предпросмотра, с"), { target: { value: "59.9" } });
    expect(screen.getByLabelText("Слой предпросмотра Logo")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Сохранить для новых" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-montage-overlays", expect.objectContaining({ template: expect.objectContaining({ layouts: { "16:9": [expect.objectContaining({ mode: "until-end", start: 6, duration: 5 })], "9:16": [] } }) })));
    fireEvent.change(screen.getByLabelText("Режим показа"), { target: { value: "once" } });
    expect((screen.getByLabelText("Длительность, с") as HTMLInputElement).value).toBe("5");
  });
  it("scans a chosen root folder, merges new random candidates and preserves existing layer settings", async () => {
    window.newsflowDesktop = { chooseFolder: vi.fn().mockResolvedValue("D:/synthetic/library") } as unknown as Window["newsflowDesktop"];
    const { command, data } = setup();
    command.mockResolvedValueOnce({ ...data, operationResult: { kind: "overlay-library", count: 3, folder: "D:/synthetic/library", skippedSymlinks: 1, assets: [
      { path: layer.path, name: "Unchanged", kind: "image" },
      { path: "D:/synthetic/library/second.png", name: "Second image", kind: "image" },
      { path: "D:/synthetic/library/clip.mp4", name: "Folder video", kind: "video" },
    ] } });
    fireEvent.click(screen.getByRole("button", { name: "Выбрать папку наложений" }));
    await waitFor(() => expect((screen.getByLabelText("Корневая папка наложений") as HTMLInputElement).value).toBe("D:/synthetic/library"));
    fireEvent.click(screen.getByRole("button", { name: "Добавить папку как случайные варианты" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Folder video" })).toBeTruthy());
    expect(command).toHaveBeenNthCalledWith(1, "scan-montage-overlays", { folder: "D:/synthetic/library" });
    expect((screen.getByLabelText("Случайная группа (пусто = всегда)") as HTMLInputElement).value).toBe("Из папки");
    fireEvent.change(screen.getByLabelText("Случайная группа (пусто = всегда)"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Second image" }));
    fireEvent.change(screen.getByLabelText("Случайная группа (пусто = всегда)"), { target: { value: "Логотип" } });
    fireEvent.click(screen.getByRole("button", { name: "Logo" }));
    expect((screen.getByLabelText("X, px") as HTMLInputElement).value).toBe("20");
    fireEvent.click(screen.getByRole("button", { name: "Сохранить для новых" }));
    await waitFor(() => expect(command).toHaveBeenCalledTimes(2));
    const saved = command.mock.calls[1][1].template;
    expect(saved.libraryRoot).toBe("D:/synthetic/library");
    expect(saved.layouts["16:9"]).toHaveLength(3);
    expect(saved.layouts["16:9"][0]).toEqual(layer);
    expect(saved.layouts["16:9"][1]).toMatchObject({ path: "D:/synthetic/library/second.png", randomGroup: "Логотип" });
    expect(saved.layouts["16:9"][2]).toMatchObject({ kind: "video", randomGroup: "", audioEnabled: false });
  });
  it("applies a typed folder's grouped template to every queue row only after confirmation", async () => {
    const { command, data } = setup({ scenarios: [{ index: 8, title: "No voice yet", state: "Готово", result: "Text", error: "" }] });
    command.mockResolvedValueOnce({ ...data, operationResult: { kind: "overlay-library", count: 2, folder: "D:/synthetic/root", skippedSymlinks: 0, assets: [
      { path: "D:/synthetic/root/one.png", name: "One candidate", kind: "image" },
      { path: "D:/synthetic/root/two.png", name: "Two candidate", kind: "image" },
    ] } });
    fireEvent.change(screen.getByLabelText("Корневая папка наложений"), { target: { value: "D:/synthetic/root" } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить папку как случайные варианты" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Two candidate" })).toBeTruthy());
    expect(screen.queryByLabelText("Слой предпросмотра One candidate")).toBeNull();
    expect(screen.getByLabelText("Слой предпросмотра Two candidate")).toBeTruthy();
    expect(screen.getByLabelText("Слой предпросмотра Logo")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "One candidate" }));
    expect(screen.getByLabelText("Слой предпросмотра One candidate")).toBeTruthy();
    expect(screen.queryByLabelText("Слой предпросмотра Two candidate")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Применить ко всей очереди (1)" }));
    expect(command).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Заменить индивидуальные" }));
    await waitFor(() => expect(command).toHaveBeenNthCalledWith(2, "save-montage-overlays", expect.objectContaining({ scope: "selected", indices: [8], overwrite: true,
      template: expect.objectContaining({ libraryRoot: "D:/synthetic/root", layouts: { "16:9": [layer, expect.objectContaining({ randomGroup: "Из папки" }), expect.objectContaining({ randomGroup: "Из папки" })], "9:16": [] } }) })));
  });
  it("uses independent image/video folders together and supports permanent candidates and source switches", async () => {
    const { command, data } = setup({ scenarios: [{ index: 12, title: "All folder groups", state: "Готово", result: "Text", error: "" }] });
    fireEvent.click(screen.getByRole("button", { name: "Добавить папку / группу" }));
    const pictures = within(screen.getByRole("group", { name: "Папка наложений 1" }));
    fireEvent.change(pictures.getByLabelText("Название группы"), { target: { value: "Картинки" } });
    fireEvent.change(pictures.getByLabelText("Папка группы"), { target: { value: "D:/synthetic/pictures" } });
    fireEvent.change(pictures.getByLabelText("Файлы группы"), { target: { value: "image" } });
    command.mockResolvedValueOnce({ ...data, operationResult: { kind: "overlay-library", count: 3, folder: "D:/synthetic/pictures", assets: [
      { path: "D:/synthetic/pictures/one.png", name: "Picture one", kind: "image" }, { path: "D:/synthetic/pictures/two.png", name: "Picture two", kind: "image" }, { path: "D:/synthetic/pictures/ignore.mp4", name: "Ignore video", kind: "video" },
    ] } });
    fireEvent.click(pictures.getByRole("button", { name: "Добавить файлы группы" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Picture two" })).toBeTruthy());
    expect(screen.queryByRole("button", { name: "Ignore video" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Добавить папку / группу" }));
    const videos = within(screen.getByRole("group", { name: "Папка наложений 2" }));
    fireEvent.change(videos.getByLabelText("Название группы"), { target: { value: "Подписка" } });
    fireEvent.change(videos.getByLabelText("Папка группы"), { target: { value: "D:/synthetic/subscribe" } });
    fireEvent.change(videos.getByLabelText("Файлы группы"), { target: { value: "video" } });
    command.mockResolvedValueOnce({ ...data, operationResult: { kind: "overlay-library", count: 3, folder: "D:/synthetic/subscribe", assets: [
      { path: "D:/synthetic/subscribe/one.mp4", name: "Subscribe one", kind: "video" }, { path: "D:/synthetic/subscribe/two.mp4", name: "Subscribe two", kind: "video" }, { path: "D:/synthetic/subscribe/ignore.png", name: "Ignore picture", kind: "image" },
    ] } });
    fireEvent.click(videos.getByRole("button", { name: "Добавить файлы группы" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Subscribe two" })).toBeTruthy());
    expect(screen.queryByRole("button", { name: "Ignore picture" })).toBeNull();
    expect(screen.getByLabelText("Слой предпросмотра Picture one")).toBeTruthy();
    expect(screen.getByLabelText("Слой предпросмотра Subscribe two")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Picture one" }));
    expect(screen.queryByLabelText("Случайная группа (пусто = всегда)")).toBeNull();
    fireEvent.click(screen.getByLabelText("Использовать постоянно"));
    expect(screen.getByLabelText("Слой предпросмотра Picture one")).toBeTruthy();
    expect(screen.getByLabelText("Слой предпросмотра Picture two")).toBeTruthy();
    fireEvent.click(videos.getByLabelText("Включить группу"));
    expect(screen.queryByLabelText("Слой предпросмотра Subscribe one")).toBeNull();
    expect(screen.getByLabelText("Слой предпросмотра Picture one")).toBeTruthy();
    fireEvent.click(videos.getByLabelText("Включить группу"));
    fireEvent.change(videos.getByLabelText("Режим группы"), { target: { value: "all" } });
    expect(screen.getByLabelText("Слой предпросмотра Subscribe one")).toBeTruthy();
    expect(screen.getByLabelText("Слой предпросмотра Subscribe two")).toBeTruthy();
    fireEvent.change(videos.getByLabelText("Файлы группы"), { target: { value: "image" } });
    expect(screen.queryByLabelText("Слой предпросмотра Subscribe one")).toBeNull();
    expect(screen.getByRole("button", { name: "Subscribe one" })).toBeTruthy();
    fireEvent.change(videos.getByLabelText("Файлы группы"), { target: { value: "video" } });
    expect(screen.getByLabelText("Слой предпросмотра Subscribe one")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Применить ко всей очереди (1)" }));
    expect(command).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: "Заменить индивидуальные" }));
    await waitFor(() => expect(command).toHaveBeenCalledTimes(3));
    expect(command.mock.calls[2][1]).toMatchObject({ scope: "selected", indices: [12], overwrite: true });
    const saved = command.mock.calls[2][1].template;
    expect(saved.librarySources).toEqual([expect.objectContaining({ name: "Картинки", root: "D:/synthetic/pictures", enabled: true, kind: "image", mode: "random" }), expect.objectContaining({ name: "Подписка", root: "D:/synthetic/subscribe", enabled: true, kind: "video", mode: "all" })]);
    expect(saved.layouts["16:9"]).toHaveLength(5);
    expect(saved.layouts["16:9"][1]).toMatchObject({ librarySourceId: saved.librarySources[0].id, randomGroup: "" });
    expect(saved.layouts["16:9"][2]).toMatchObject({ librarySourceId: saved.librarySources[0].id, randomGroup: "Картинки" });
    expect(saved.layouts["16:9"][3]).toMatchObject({ librarySourceId: saved.librarySources[1].id, audioEnabled: false });
  });
  it("keeps independent layers for a shared manual/source-A/source-B file and deduplicates rescans only within their source", async () => {
    const sharedPath = "D:/synthetic/shared/logo.png";
    const manual = { ...layer, path: sharedPath };
    const { command, data } = setup({ montageSettings: { ...fallback.montageSettings, overlayTemplate: { version: 1, layouts: { "16:9": [manual], "9:16": [] } } } });
    const scanResult = (folder: string) => ({ ...data, operationResult: { kind: "overlay-library", count: 1, folder, assets: [{ path: sharedPath, name: "Shared image", kind: "image" as const }] } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить папку / группу" }));
    const sourceA = within(screen.getByRole("group", { name: "Папка наложений 1" }));
    fireEvent.change(sourceA.getByLabelText("Название группы"), { target: { value: "Source A" } });
    fireEvent.change(sourceA.getByLabelText("Папка группы"), { target: { value: "D:/synthetic" } });
    command.mockResolvedValueOnce(scanResult("D:/synthetic"));
    fireEvent.click(sourceA.getByRole("button", { name: "Добавить файлы группы" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Shared image" })).toBeTruthy());
    fireEvent.change(screen.getByLabelText("X, px"), { target: { value: "101" } });
    command.mockResolvedValueOnce(scanResult("D:/synthetic"));
    fireEvent.click(sourceA.getByRole("button", { name: "Добавить файлы группы" }));
    await waitFor(() => expect(command).toHaveBeenCalledTimes(2));
    await waitFor(() => expect((screen.getByRole("button", { name: "Добавить папку / группу" }) as HTMLButtonElement).matches(":disabled")).toBe(false));
    expect(screen.getAllByRole("button", { name: "Shared image" })).toHaveLength(1);
    expect((screen.getByLabelText("X, px") as HTMLInputElement).value).toBe("101");
    fireEvent.click(screen.getByRole("button", { name: "Добавить папку / группу" }));
    const sourceB = within(screen.getByRole("group", { name: "Папка наложений 2" }));
    fireEvent.change(sourceB.getByLabelText("Название группы"), { target: { value: "Source B" } });
    fireEvent.change(sourceB.getByLabelText("Папка группы"), { target: { value: "D:/synthetic/shared" } });
    command.mockResolvedValueOnce(scanResult("D:/synthetic/shared"));
    fireEvent.click(sourceB.getByRole("button", { name: "Добавить файлы группы" }));
    await waitFor(() => expect(screen.getAllByRole("button", { name: "Shared image" })).toHaveLength(2));
    fireEvent.change(screen.getByLabelText("X, px"), { target: { value: "202" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Shared image" })[0]);
    expect((screen.getByLabelText("X, px") as HTMLInputElement).value).toBe("101");
    fireEvent.change(screen.getByLabelText("Корневая папка наложений"), { target: { value: "D:/synthetic" } });
    command.mockResolvedValueOnce(scanResult("D:/synthetic"));
    fireEvent.click(screen.getByRole("button", { name: "Добавить папку как случайные варианты" }));
    await waitFor(() => expect(command).toHaveBeenCalledTimes(4));
    await waitFor(() => expect((screen.getByRole("button", { name: "Сохранить для новых" }) as HTMLButtonElement).matches(":disabled")).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить для новых" }));
    await waitFor(() => expect(command).toHaveBeenCalledTimes(5));
    const saved = command.mock.calls[4][1].template;
    expect(saved.layouts["16:9"]).toHaveLength(3);
    expect(saved.layouts["16:9"][0]).toEqual(manual);
    expect(saved.layouts["16:9"][1]).toMatchObject({ path: sharedPath, x: 101, librarySourceId: saved.librarySources[0].id });
    expect(saved.layouts["16:9"][2]).toMatchObject({ path: sharedPath, x: 202, librarySourceId: saved.librarySources[1].id });
  });
});
