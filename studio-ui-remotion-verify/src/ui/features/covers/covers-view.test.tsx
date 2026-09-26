import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { CoverGallery, Covers, fallback } from "../../App";
import { coverWordPairGenerationPayload } from "../../thumbnail-word-actions";

const coverStyles = readFileSync(resolve(process.cwd(), "src/ui/covers.css"), "utf8");
const responsiveStyles = readFileSync(resolve(process.cwd(), "src/ui/layout/app-shell-responsive.css"), "utf8");

describe("Covers Light view", () => {
  it("preserves durable identities in paired cover-word payloads", () => {
    expect(coverWordPairGenerationPayload({
      indices: [7],
      productionItemIds: ["production:7"],
      provider: "agent",
      useStructure: true,
      avoidRepeats: false,
    })).toEqual({
      indices: [7],
      productionItemIds: ["production:7"],
      provider: "agent",
      useDefault: true,
      useStructure: true,
      avoidRepeats: false,
    });
  });

  it("keeps the current cover controls inside the Visual Production Studio", () => {
    render(<Covers data={fallback} command={vi.fn(async () => undefined)} />);

    expect(screen.getByLabelText("Visual Production Studio")).toBeTruthy();
    expect(screen.getByLabelText("Конвейер создания обложки")).toBeTruthy();
  });

  it("keeps the verified FastGen cover-start contract", async () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      covers: [{ title: "Ормуз", image_prompt: "Танкер в Ормузе", paths: [] }],
    };
    render(<Covers data={data} command={command} />);

    fireEvent.click(screen.getByText("Создать обложки").closest("button")!);

    await waitFor(() => expect(command).toHaveBeenCalledWith("generate-covers", expect.objectContaining({
      indices: [], resumeGeneration: true, operation: data.coverSettings.operation,
      buildMode: "fastgen-full", faceMode: "auto", textMode: "fastgen", localFaceOnly: false,
    })));
  });

  it("exposes exactly the two all-FastGen routes and sends the my-faces route", async () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      covers: [{ title: "Порт Одессы", image_prompt: "Морской терминал", paths: [] }],
    };
    render(<Covers data={data} command={command} />);

    expect(screen.getByRole("button", { name: "Всё через FastGen" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "FastGen всё + мои лица" })).toBeTruthy();
    expect(screen.queryByText("FastGen + NewsFlow всё")).toBeNull();
    expect(screen.queryByText("FastGen текст + лицо NewsFlow")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "FastGen всё + мои лица" }));
    fireEvent.click(screen.getByText("Создать обложки").closest("button")!);

    await waitFor(() => expect(command).toHaveBeenCalledWith("generate-covers", expect.objectContaining({
      buildMode: "fastgen-full-my-face", faceMode: "auto", textMode: "fastgen", localFaceOnly: false,
    })));
  });

  it("does not submit the cover-start sequence twice while the current command is pending", async () => {
    let releaseCurrentCommand: (() => void) | undefined;
    const command = vi.fn(() => new Promise<NewsFlowSnapshot | undefined>((resolve) => {
      releaseCurrentCommand = () => resolve(undefined);
    }));
    const data = {
      ...fallback,
      covers: [{ title: "Ормуз", image_prompt: "Танкер в Ормузе", paths: [] }],
    };
    render(<Covers data={data} command={command} />);

    const start = screen.getByText("Создать обложки").closest("button")!;
    fireEvent.click(start);
    fireEvent.click(start);

    await Promise.resolve();
    expect(command).toHaveBeenCalledTimes(1);
    expect(command).toHaveBeenCalledWith("save-cover-settings", expect.any(Object));
    releaseCurrentCommand?.();
  });

  it("keeps the current Universal V2 prompt-generation command", async () => {
    const command = vi.fn(async () => undefined);
    render(<Covers data={fallback} command={command} />);

    fireEvent.click(screen.getAllByText(/Создать 2 промпта/)[0].closest("button")!);
    await Promise.resolve();
    await Promise.resolve();
    expect(command).toHaveBeenCalledWith("generate-cover-prompts", { indices: [], provider: "agent" });
  });

  it("keeps explicit all and selected bulk actions on the current cover queue", async () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      covers: [{
        production_item_id: "production:ormuz",
        title: "Ормуз",
        image_prompt: "",
        paths: [],
      }],
    };
    render(<Covers data={data} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "Создать промпты всем" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "generate-cover-prompts",
      { indices: [], provider: "agent" },
    ));

    fireEvent.click(screen.getByRole("button", { name: "Выбрать: Ормуз" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Создать промпты выбранным" })[0]);
    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "generate-cover-prompts",
      { indices: [0], productionItemIds: ["production:ormuz"], provider: "agent" },
    ));

    fireEvent.click(screen.getByRole("button", { name: "Придумать заголовки и подзаголовки — всем" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "generate-cover-texts",
      {
        indices: [],
        provider: "agent",
        useDefault: true,
        useStructure: true,
        avoidRepeats: true,
      },
    ));

    command.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Придумать заголовки и подзаголовки — выбранным" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "generate-cover-texts",
      {
        indices: [0],
        productionItemIds: ["production:ormuz"],
        provider: "agent",
        useDefault: true,
        useStructure: true,
        avoidRepeats: true,
      },
    ));
    expect(command).not.toHaveBeenCalledWith(
      "generate-cover-texts",
      expect.objectContaining({ indices: [] }),
    );
  });

  it("exposes truthful independent pause and continue controls", () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      covers: [{ production_item_id: "production:ormuz", title: "Ормуз", paths: [] }],
      coverSettings: {
        ...fallback.coverSettings,
        headlinePaused: false,
        subheadlinePaused: true,
      },
    };
    render(<Covers data={data} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Настроить студию" }));

    expect(screen.getByRole("button", { name: "Пауза заголовков" }).hasAttribute("disabled")).toBe(false);
    expect(screen.getByRole("button", { name: "Продолжить заголовки" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "Пауза подзаголовков" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "Продолжить подзаголовки" }).hasAttribute("disabled")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Продолжить подзаголовки" }));
    expect(command).toHaveBeenCalledTimes(1);
    expect(command).toHaveBeenCalledWith("resume-cover-text-generation", { kind: "subheadline" });
    expect(command).not.toHaveBeenCalledWith("generate-cover-subheadlines", expect.anything());
  });

  it("keeps pause, continue, and start as three explicit cover-render controls", () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      covers: [{ production_item_id: "production:ormuz", title: "Ормуз", image_prompt: "scene", paths: [] }],
      coverSettings: { ...fallback.coverSettings, generationPaused: false },
    };
    const { rerender } = render(<Covers data={data} command={command} />);

    expect(screen.getByRole("button", { name: "Пауза генерации" }).hasAttribute("disabled")).toBe(false);
    expect(screen.getByRole("button", { name: "Продолжить генерацию" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "Запустить готовые" })).toBeTruthy();

    rerender(<Covers data={{ ...data, coverSettings: { ...data.coverSettings, generationPaused: true } }} command={command} />);
    expect(screen.getByRole("button", { name: "Пауза генерации" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "Продолжить генерацию" }).hasAttribute("disabled")).toBe(false);
  });

  it("supports Ctrl multi-select and sends exact ordered durable scope for new prompts", async () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      covers: [
        { production_item_id: "production:z", title: "A", image_prompt: "old A", paths: [] },
        { production_item_id: "production:a", title: "B", image_prompt: "old B", paths: [] },
        { production_item_id: "production:c", title: "C", image_prompt: "old C", paths: [] },
      ],
    };
    render(<Covers data={data} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "Выбрать: A" }));
    fireEvent.click(screen.getByRole("button", { name: "Выбрать: B" }), { ctrlKey: true });
    expect(screen.getByText("Выбрано: 2")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Снять выбор: A" }), { ctrlKey: true });
    expect(screen.getByText("Выбрано: 1")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Выбрать: A" }), { ctrlKey: true });

    fireEvent.click(screen.getByRole("button", { name: "Перегенерировать промпты выбранным" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "regenerate-covers-new-prompts",
      { indices: [1, 0], productionItemIds: ["production:a", "production:z"], provider: "agent" },
    ));

    fireEvent.click(screen.getByRole("button", { name: "Выбрать: C" }));
    expect(screen.getByText("Выбрано: 1")).toBeTruthy();
  });

  it("supports Shift ranges in the lower ready-cover queue", () => {
    const data = {
      ...fallback,
      covers: [
        { production_item_id: "production:a", title: "A", image_prompt: "A", paths: ["a.png"] },
        { production_item_id: "production:b", title: "B", image_prompt: "B", paths: ["b.png"] },
        { production_item_id: "production:c", title: "C", image_prompt: "C", paths: ["c.png"] },
        { production_item_id: "production:d", title: "D", image_prompt: "D", paths: ["d.png"] },
      ],
    };
    render(<Covers data={data} command={vi.fn(async () => undefined)} />);

    fireEvent.click(screen.getByRole("button", { name: "Выбрать: B" }));
    fireEvent.click(screen.getByRole("button", { name: "Выбрать: D" }), { shiftKey: true });

    expect(screen.getByText("Выбрано: 3")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Снять выбор: B" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Снять выбор: C" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Снять выбор: D" })).toBeTruthy();
  });

  it("edits unlimited build-mode ranges and the varied palette policy", async () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      covers: [
        { production_item_id: "production:a", title: "A", image_prompt: "A", paths: [] },
        { production_item_id: "production:b", title: "B", image_prompt: "B", paths: [] },
      ],
      coverSettings: {
        ...fallback.coverSettings,
        buildModeRanges: [],
        allowVariedTextPalette: false,
      },
    };
    render(<Covers data={data} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "Добавить диапазон режимов" }));
    expect(screen.getAllByLabelText("Начало диапазона режима")).toHaveLength(1);
    fireEvent.change(screen.getByLabelText("Конец диапазона режима"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Режим диапазона"), { target: { value: "fastgen-full-my-face" } });
    fireEvent.click(screen.getByLabelText("Разрешить разные цветовые схемы текста и плашки"));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить диапазоны режимов" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "save-cover-settings",
      expect.objectContaining({
        buildModeRanges: [{ start: 1, end: 2, buildMode: "fastgen-full-my-face" }],
        allowVariedTextPalette: true,
      }),
    ));
  });

  it("manually retries only an exact eligible durable selection with the current render contract", async () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      covers: [
        { production_item_id: "production:z", title: "A", image_prompt: "same A", status: "Ошибка FastGen", error: "terminal A", paths: [] },
        { production_item_id: "production:a", title: "B", image_prompt: "same B", status: "Нужен новый промпт", error: "terminal B", paths: [] },
      ],
    };
    render(<Covers data={data} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "Выбрать: B" }));
    fireEvent.click(screen.getByRole("button", { name: "Выбрать: A" }), { ctrlKey: true });
    const retry = screen.getByRole("button", { name: "Повторить генерацию выбранных" });
    expect(retry.hasAttribute("disabled")).toBe(false);
    fireEvent.click(retry);

    expect(command).toHaveBeenCalledWith("retry-cover-generation", {
      indices: [1, 0],
      productionItemIds: ["production:a", "production:z"],
    });
    expect(command).not.toHaveBeenCalledWith("regenerate-covers-new-prompts", expect.anything());
  });

  it("disables manual retry for an active or mixed selected render without dropping rows", () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      covers: [
        { production_item_id: "production:error", title: "Error", image_prompt: "same", status: "Ошибка FastGen", error: "terminal", paths: [] },
        { production_item_id: "production:active", title: "Active", image_prompt: "same", status: "Подготовка запросов", paths: [] },
        { production_item_id: "production:accepted", title: "Accepted", image_prompt: "same", status: "Ошибка FastGen", error: "polling interrupted", accepted_generation_id: "task-1", paths: [] },
      ],
    };
    render(<Covers data={data} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Выбрать: Error" }));
    fireEvent.click(screen.getByRole("button", { name: "Выбрать: Active" }), { ctrlKey: true });
    fireEvent.click(screen.getByRole("button", { name: "Выбрать: Accepted" }), { ctrlKey: true });

    expect(screen.getByText("Повтор генерации доступен: 1/3")).toBeTruthy();
    const retry = screen.getByRole("button", { name: "Повторить генерацию выбранных" });
    expect(retry.hasAttribute("disabled")).toBe(true);
    fireEvent.click(retry);
    expect(command).not.toHaveBeenCalledWith("retry-cover-generation", expect.anything());
  });

  it("keeps new-prompt creation separate and does not start a manual render", async () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      covers: [{ production_item_id: "production:error", title: "Error", image_prompt: "rejected", status: "Нужен новый промпт", error: "terminal", paths: [] }],
    };
    render(<Covers data={data} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Выбрать: Error" }));
    fireEvent.click(screen.getByRole("button", { name: "Перегенерировать промпты выбранным" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "regenerate-covers-new-prompts",
      { indices: [0], productionItemIds: ["production:error"], provider: "agent" },
    ));
    expect(command).not.toHaveBeenCalledWith("retry-cover-generation", expect.anything());
    expect(command).not.toHaveBeenCalledWith("regenerate-covers", expect.anything());
    expect(command).not.toHaveBeenCalledWith("generate-covers", expect.anything());
  });

  it("shows selected new-prompt readiness and blocks bulk render until all selected rows are ready", () => {
    const command = vi.fn(async () => undefined);
    const baseCovers = [
      { production_item_id: "production:a", title: "A", image_prompt: "new A", paths: [] },
      { production_item_id: "production:b", title: "B", image_prompt: "new B", paths: [] },
    ];
    const data = { ...fallback, covers: baseCovers };
    const { rerender } = render(<Covers data={data} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Выбрать: A" }));
    fireEvent.click(screen.getByRole("button", { name: "Выбрать: B" }), { ctrlKey: true });

    expect(screen.getByText("Новые промпты готовы: 0/2")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Перегенерировать обложки выбранным" }).hasAttribute("disabled")).toBe(true);

    rerender(<Covers data={{ ...data, covers: [
      { ...baseCovers[0], status: "Новые промпты созданы" }, baseCovers[1],
    ] }} command={command} />);
    expect(screen.getByText("Новые промпты готовы: 1/2")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Перегенерировать обложки выбранным" }).hasAttribute("disabled")).toBe(true);

    rerender(<Covers data={{ ...data, covers: baseCovers.map((cover) => ({ ...cover, status: "Новые промпты созданы" })) }} command={command} />);
    expect(screen.getByText("Новые промпты готовы: 2/2")).toBeTruthy();
    const renderSelected = screen.getByRole("button", { name: "Перегенерировать обложки выбранным" });
    expect(renderSelected.hasAttribute("disabled")).toBe(false);
    fireEvent.click(renderSelected);
    expect(command).toHaveBeenCalledWith("regenerate-covers", expect.objectContaining({
      indices: [0, 1], productionItemIds: ["production:a", "production:b"],
      currentProfile: false, useBuildModeRanges: true,
    }));
  });

  it("shows a partial prompt rewrite failure without a false all-ready state", () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      covers: [
        { production_item_id: "production:a", title: "A", image_prompt: "new A", status: "Новые промпты созданы", paths: [] },
        { production_item_id: "production:b", title: "B", image_prompt: "old B", status: "Ошибка промпта", error: "provider rejected", paths: [] },
      ],
    };
    render(<Covers data={data} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Выбрать: A" }));
    fireEvent.click(screen.getByRole("button", { name: "Выбрать: B" }), { ctrlKey: true });

    expect(screen.getByText("Новые промпты: 1/2 готовы · ошибок: 1")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Перегенерировать обложки выбранным" }).hasAttribute("disabled")).toBe(true);
  });

  it("offers confirmed selected and all image cleanup without treating empty selection as all", () => {
    const command = vi.fn(async () => undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const data = {
      ...fallback,
      covers: [{ production_item_id: "production:a", title: "A", image_prompt: "scene", paths: ["a.png"] }],
    };
    render(<Covers data={data} command={command} />);

    const selectedCleanup = screen.getByRole("button", { name: "Удалить картинки — выбранные" });
    expect(selectedCleanup.hasAttribute("disabled")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Выбрать: A" }));
    fireEvent.click(selectedCleanup);
    expect(command).toHaveBeenCalledWith("remove-cover-results", { indices: [0], productionItemIds: ["production:a"] });

    fireEvent.click(screen.getByRole("button", { name: "Удалить картинки — все" }));
    expect(command).toHaveBeenCalledWith("remove-cover-results", { all: true });
  });

  it("shows truthful queue statuses and retry attempt detail per cover", () => {
    const statuses = [
      "Ожидает",
      "Подготовка запросов",
      "Круг 2/4 · попытка 1/4",
      "Приостановлено",
      "Ожидает лимит FastGen",
      "Готово",
      "Ошибка FastGen",
      "Новые промпты созданы",
    ];
    const data = {
      ...fallback,
      covers: statuses.map((status, index) => ({
        production_item_id: `production:${index}`,
        title: `Тема ${index}`,
        image_prompt: `scene ${index}`,
        status,
        paths: [],
        timeline: status.startsWith("Круг")
          ? [{ at: "12:00:00", label: status, progress: 25, detail: "всего попытка 7/16" }]
          : [],
      })),
    };
    render(<Covers data={data} command={vi.fn(async () => undefined)} />);

    for (const status of statuses) expect(screen.getAllByText(status).length).toBeGreaterThan(0);
    expect(screen.getByText("всего попытка 7/16")).toBeTruthy();
  });

  it("uses the workstation queue and opens the selected cover in an inspector", () => {
    const data = {
      ...fallback,
      covers: [{ title: "Ормуз", image_prompt: "Танкер в Ормузе", paths: [] }],
    };
    render(<Covers data={data} command={vi.fn(async () => undefined)} />);

    expect(screen.getByRole("table", { name: "Очередь обложек" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "1. Ормуз" }));
    expect(screen.getByText("Инспектор обложки")).toBeTruthy();
  });

  it("opens a cover inspector with FastGen prompt provenance", () => {
    const data = {
      ...fallback,
      covers: [{
        production_item_id: "item-ormuz",
        title: "Ормуз",
        image_prompt: "Танкер в Ормузе",
        prompt_provider: "agent",
        prompt_sources: { SCENE: "Topic Planner" },
        faceSelectionMode: "semantic-only" as const,
        faceSelectionReason: "topic-relevant face-tree metadata match",
        semantic_face_label: "Трамп",
        render_profile: { build_mode: "fastgen-full", text_mode: "fastgen" },
        final_provider_prompt: "FINAL PROMPT MARKER",
        paths: [],
      }],
    };
    render(<Covers data={data} command={vi.fn(async () => undefined)} />);

    fireEvent.keyDown(screen.getAllByRole("row")[1], { key: "Enter" });
    expect(screen.getByText("Инспектор обложки")).toBeTruthy();
    expect(screen.getByText("ProductionItem ID")).toBeTruthy();
    expect(screen.getByText("item-ormuz")).toBeTruthy();
    expect(screen.getByText("agent")).toBeTruthy();
    expect(screen.getByText("Topic Planner")).toBeTruthy();
    expect(screen.getByText(/semantic-only · Трамп/)).toBeTruthy();
    expect(screen.getByText("Режим FastGen")).toBeTruthy();
    expect(screen.getByText("fastgen-full")).toBeTruthy();
    expect(screen.getByText("0 · лицо задано семантически")).toBeTruthy();
    expect(screen.getByText("Final FastGen prompt")).toBeTruthy();
    expect(screen.getByText("FINAL PROMPT MARKER")).toBeTruthy();
  });

  it("keeps advanced FastGen configuration out of the primary production queue", () => {
    render(<Covers data={fallback} command={vi.fn(async () => undefined)} />);

    fireEvent.click(screen.getByRole("button", { name: "Настроить студию" }));
    expect(screen.getByRole("dialog", { name: "Настройки Visual Production Studio" })).toBeTruthy();
    expect(screen.getByText("1. Рендер FastGen")).toBeTruthy();
  });

  it("uses a result index before opening one gallery item inspector", () => {
    const data = {
      ...fallback,
      covers: [{ title: "Ормуз", image_prompt: "Танкер в Ормузе", paths: [] }],
    };
    render(<CoverGallery data={data} command={vi.fn(async () => undefined)} />);

    expect(screen.getByRole("table", { name: "Галерея результатов" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "1. Ормуз" }));
    expect(screen.getByRole("dialog", { name: "Инспектор результата обложки" })).toBeTruthy();
  });

  it("keeps gallery context and metrics readable beside the workstation inspector", () => {
    expect(coverStyles).toContain(".cover-gallery-hero{display:grid;grid-template-columns:minmax(0,1fr) minmax(280px,360px)");
    expect(coverStyles).toContain(".cover-gallery-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr))");
  });

  it("collapses Cover workspace grids by available main-column width, not only viewport width", () => {
    expect(responsiveStyles).toContain("@container (max-width:980px)");
    expect(responsiveStyles).toContain(".nf-covers .covers-workspace{grid-template-columns:minmax(0,1fr)}");
    expect(responsiveStyles).toContain(".nf-covers .cover-studio-hero{align-items:flex-start;flex-direction:column}");
    expect(responsiveStyles).toContain(".nf-covers .cover-hero-metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))");
  });
});
