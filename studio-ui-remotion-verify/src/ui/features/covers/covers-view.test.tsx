import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { CoverGallery, Covers, fallback } from "../../App";
import { coverWordPairGenerationPayload } from "../../thumbnail-word-actions";

const coverStyles = readFileSync(resolve(process.cwd(), "src/ui/covers.css"), "utf8");
const responsiveStyles = readFileSync(resolve(process.cwd(), "src/ui/layout/app-shell-responsive.css"), "utf8");
const componentStyles = readFileSync(resolve(process.cwd(), "src/ui/components/components.css"), "utf8");

describe("Covers Light view", () => {
  it("adds standalone topic/prompt pairs from an empty cover queue with an explicit create command", async () => {
    let finish: (value: typeof fallback) => void = () => undefined;
    const command = vi.fn(() => new Promise<typeof fallback>((resolve) => { finish = resolve; }));
    render(<Covers data={{ ...fallback, covers: [], scenarios: [] }} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Добавить темы и промпты" }));
    const source = "Сад: теплица\nA greenhouse\nХлеб\nFresh bread";
    fireEvent.change(screen.getByLabelText("Темы и промпты"), { target: { value: source } });
    const add = screen.getByRole("button", { name: "Добавить в обложки" });
    fireEvent.click(add);
    fireEvent.click(add);
    expect(command).toHaveBeenCalledTimes(1);
    expect(command).toHaveBeenCalledWith("import-cover-prompt-pairs", { text: source, createMissingTopics: true });
    finish(fallback);
    await waitFor(() => expect(screen.queryByLabelText("Темы и промпты")).toBeNull());
  });

  it("keeps standalone input for retry if the backend rejects the batch", async () => {
    const command = vi.fn(async () => undefined);
    render(<Covers data={{ ...fallback, covers: [] }} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Добавить темы и промпты" }));
    fireEvent.change(screen.getByLabelText("Темы и промпты"), { target: { value: "Тема\nПромпт\nБез пары" } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить в обложки" }));
    await screen.findByRole("alert");
    expect(screen.getByLabelText("Темы и промпты")).toHaveProperty("value", "Тема\nПромпт\nБез пары");
    expect(command).toHaveBeenCalledTimes(1);
  });

  it("loads a TXT into the standalone editor without starting generation", async () => {
    const chooseCoverPromptPairs = vi.fn(async () => "Тема\nReady prompt");
    Object.assign(window, { newsflowDesktop: { chooseCoverPromptPairs } });
    const command = vi.fn();
    render(<Covers data={{ ...fallback, covers: [] }} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Добавить темы и промпты" }));
    fireEvent.click(screen.getByRole("button", { name: "Загрузить пары из TXT" }));
    await waitFor(() => expect(screen.getByLabelText("Темы и промпты")).toHaveProperty("value", "Тема\nReady prompt"));
    expect(command).not.toHaveBeenCalled();
  });

  it("keeps the Visual Production Studio sheet bounded when a setting has a long value", () => {
    expect(componentStyles).toMatch(/\.nf-sheet-content\{[^}]*min-width:0[^}]*overflow:hidden/);
    expect(componentStyles).toMatch(/\.nf-sheet-body\{[^}]*min-width:0[^}]*overflow:auto/);
  });

  it("imports manual prompt pairs through one chooser and one durable command", async () => {
    let finishChoose: (value: string) => void = () => undefined;
    const chooseCoverPromptPairs = vi.fn(() => new Promise<string>((resolve) => {
      finishChoose = resolve;
    }));
    Object.assign(window, { newsflowDesktop: { chooseCoverPromptPairs } });
    const command = vi.fn(async () => fallback);
    render(<Covers data={fallback} command={command} />);

    const button = screen.getByRole("button", { name: "Импортировать промпты TXT" });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(chooseCoverPromptPairs).toHaveBeenCalledTimes(1);

    finishChoose("Тема\nManual visual prompt");
    await waitFor(() => expect(command).toHaveBeenCalledWith("import-cover-prompt-pairs", {
      text: "Тема\nManual visual prompt",
    }));
    await waitFor(() => expect(button).toHaveProperty("disabled", false));
  });

  it("keeps prompt import local when the chooser rejects a binary TXT", async () => {
    const chooseCoverPromptPairs = vi.fn().mockRejectedValue(
      new Error("TXT содержит недопустимые управляющие символы."),
    );
    Object.assign(window, { newsflowDesktop: { chooseCoverPromptPairs } });
    const command = vi.fn();
    render(<Covers data={fallback} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "Импортировать промпты TXT" }));
    expect((await screen.findByRole("alert")).textContent).toContain("недопустимые управляющие символы");
    expect(command).not.toHaveBeenCalled();
  });

  it("imports complete manual cover-text triples through one chooser and one durable command", async () => {
    let finishChoose: (value: string) => void = () => undefined;
    const chooseCoverTextTriples = vi.fn(() => new Promise<string>((resolve) => {
      finishChoose = resolve;
    }));
    Object.assign(window, { newsflowDesktop: { chooseCoverTextTriples } });
    const command = vi.fn(async () => fallback);
    render(<Covers data={fallback} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "Настроить студию" }));
    const button = await screen.findByRole("button", { name: "Импортировать тексты TXT" });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(chooseCoverTextTriples).toHaveBeenCalledTimes(1);

    finishChoose("Тема\nМОЙ HEADLINE\nМОЙ SUBHEADLINE");
    await waitFor(() => expect(command).toHaveBeenCalledWith("import-cover-text-triples", {
      text: "Тема\nМОЙ HEADLINE\nМОЙ SUBHEADLINE",
    }));
    await waitFor(() => expect(button).toHaveProperty("disabled", false));
  });

  it("treats cancellation as a no-op and keeps binary TXT errors out of the core command", async () => {
    const chooseCoverTextTriples = vi.fn()
      .mockResolvedValueOnce("")
      .mockRejectedValueOnce(new Error("TXT содержит недопустимые управляющие символы."));
    Object.assign(window, { newsflowDesktop: { chooseCoverTextTriples } });
    const command = vi.fn();
    render(<Covers data={fallback} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "Настроить студию" }));
    const button = await screen.findByRole("button", { name: "Импортировать тексты TXT" });
    fireEvent.click(button);
    await waitFor(() => expect(button).toHaveProperty("disabled", false));
    expect(command).not.toHaveBeenCalled();

    fireEvent.click(button);
    expect((await screen.findByRole("alert")).textContent).toContain("недопустимые управляющие символы");
    expect(command).not.toHaveBeenCalled();
    await waitFor(() => expect(button).toHaveProperty("disabled", false));
  });

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

  it("shows an explicit tabloid toggle and forwards it to cover-word generation", async () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      covers: [{ production_item_id: "production:test", title: "Границы закрыты", paths: [] }],
    };
    render(<Covers data={data} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "Настроить студию" }));
    const toggle = await screen.findByLabelText("Жёлтая пресса / максимально кликбейтный стиль");
    expect(toggle.closest("label")?.textContent).toContain("STANDARD");
    expect(coverStyles).toContain(".cover-tabloid-toggle");

    fireEvent.click(toggle);
    expect(toggle.closest("label")?.textContent).toContain("TABLOID");

    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "save-cover-settings",
      { tabloidMode: true },
    ));

    fireEvent.click(screen.getByRole("button", { name: "Придумать заголовки и подзаголовки — всем" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "generate-cover-texts",
      expect.objectContaining({ tabloidMode: true }),
    ));
  });

  it("persists the optional intensified-scene mode", async () => {
    const command = vi.fn(async () => undefined);
    render(<Covers data={fallback} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "Настроить студию" }));
    const toggle = await screen.findByLabelText("Усилить драматургию сцен");
    fireEvent.click(toggle);

    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "save-cover-settings",
      { sceneIntensityMode: true },
    ));
  });

  it("keeps the documented Gemini Nano Banana 2 model visible before FastGen refresh", async () => {
    const command = vi.fn(async () => undefined);
    render(<Covers data={fallback} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "Настроить студию" }));
    const operation = screen.getByLabelText("Активная модель");
    expect(
      screen.getByRole("option", { name: /Gemini.*Nano Banana 2.*1 credit/i }),
    ).toBeTruthy();
    fireEvent.change(operation, { target: { value: "gemini_nano_banana_2_image_generate" } });

    await waitFor(() =>
      expect(command).toHaveBeenCalledWith("save-cover-settings", {
        operation: "gemini_nano_banana_2_image_generate",
      }),
    );
  });

  it("keeps Nano Banana 2 visible beside an older cached FastGen catalogue", () => {
    const data = {
      ...fallback,
      fastgenCapabilities: {
        ...fallback.fastgenCapabilities,
        image: [{
          id: "flower_image_generate",
          provider: "Flower",
          display_name: "Flower Image",
          health: "healthy" as const,
          health_label: "Доступна по API",
          billing: { credits: 2, display: "2 credits" },
        }],
      },
    };

    render(<Covers data={data} command={vi.fn(async () => undefined)} />);
    fireEvent.click(screen.getByRole("button", { name: "Настроить студию" }));

    expect(screen.getByRole("option", { name: /Flower.*2 credits/i })).toBeTruthy();
    expect(
      screen.getByRole("option", { name: /Gemini.*Nano Banana 2.*1 credit/i }),
    ).toBeTruthy();
    expect(screen.getByText(/CACHED \+ CATALOG/i)).toBeTruthy();
    expect(screen.getByText(/сохранённый FastGen-кэш \+ документированный каталог/i)).toBeTruthy();
  });

  it("drops catalog-only routes after a successful FastGen refresh makes the API authoritative", async () => {
    const cached = {
      ...fallback,
      fastgenCapabilities: {
        ...fallback.fastgenCapabilities,
        image: [{
          id: "flower_image_generate",
          provider: "Flower",
          display_name: "Flower Image",
          health: "healthy" as const,
          health_label: "Доступна по API",
        }],
      },
    };
    const command = vi.fn(async () => cached);

    render(<Covers data={cached} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Настроить студию" }));

    expect(
      screen.getByRole("option", { name: /Gemini.*Nano Banana 2.*1 credit/i }),
    ).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Обновить модели" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith("refresh-fastgen"));
    await waitFor(() =>
      expect(screen.queryByRole("option", { name: /Nano Banana 2/i })).toBeNull(),
    );
    expect(screen.getByText(/LIVE/i)).toBeTruthy();
  });

  it("treats an empty successful FastGen refresh as authoritative LIVE data", async () => {
    const command = vi.fn(async () => fallback);
    render(<Covers data={fallback} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "Настроить студию" }));
    expect(
      screen.getByRole("option", { name: /Gemini.*Nano Banana 2.*1 credit/i }),
    ).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Обновить модели" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith("refresh-fastgen"));
    await waitFor(() =>
      expect(screen.queryByRole("option", { name: /Nano Banana 2/i })).toBeNull(),
    );
    expect(screen.getByText(/LIVE/i)).toBeTruthy();
  });

  it("lets matching live FastGen metadata override the Nano Banana 2 catalogue fallback", () => {
    const data = {
      ...fallback,
      fastgenCapabilities: {
        ...fallback.fastgenCapabilities,
        image: [{
          id: "gemini_nano_banana_2_image_generate",
          provider: "Gemini Live",
          model: "gemini-nano-banana-2",
          display_name: "Nano Banana 2 Live",
          health: "healthy" as const,
          health_label: "Доступна по API",
          billing: { credits: 3, display: "3 live credits" },
        }],
      },
    };

    render(<Covers data={data} command={vi.fn(async () => undefined)} />);
    fireEvent.click(screen.getByRole("button", { name: "Настроить студию" }));

    expect(
      screen.getByRole("option", { name: /Gemini Live.*Nano Banana 2 Live.*3 live credits/i }),
    ).toBeTruthy();
    expect(screen.queryByRole("option", { name: /Nano Banana 2.*1 credit/i })).toBeNull();
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

  it("sends exact durable IDs when the primary FastGen action targets all visible topics", async () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      covers: [
        { production_item_id: "production:a", title: "A", image_prompt: "scene A", paths: [] },
        { production_item_id: "production:b", title: "B", image_prompt: "scene B", paths: [] },
      ],
    };
    render(<Covers data={data} command={command} />);

    fireEvent.click(screen.getByText("Создать обложки").closest("button")!);

    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "generate-covers",
      expect.objectContaining({
        indices: [],
        productionItemIds: ["production:a", "production:b"],
        resumeGeneration: true,
      }),
    ));
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

  it("keeps explicit FastGen visual references in step 02 and persists their mode contract", async () => {
    const command = vi.fn(async () => undefined);
    render(<Covers data={fallback} command={command} />);

    const toggle = screen.getByLabelText("Использовать референсы FastGen");
    expect(toggle.closest("article")?.textContent).toContain("Выберите движок текста и лица");
    fireEvent.click(toggle);
    expect(screen.getByText("Стиль")).toBeTruthy();
    expect(screen.getByText("Композиция")).toBeTruthy();
    expect(screen.getByText("Атмосфера / цвет / свет")).toBeTruthy();
    expect(screen.getByText("Авто")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Сохранить референсы FastGen" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-cover-settings", expect.objectContaining({
      useReferences: true,
      referenceImagePaths: [],
      referenceModeAuto: false,
    })));
  });

  it("never promises more visual references than the active FastGen route can send", () => {
    const data = {
      ...fallback,
      coverSettings: {
        ...fallback.coverSettings,
        referenceProviderLimit: 4,
        referenceWillSendCount: 4,
        referenceWillSendCountMyFaces: 3,
      },
    };
    render(<Covers data={data} command={vi.fn(async () => undefined)} />);

    fireEvent.click(screen.getByLabelText("Использовать референсы FastGen"));
    expect(screen.getByText(/будет отправлено до 4 визуальных референсов/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "FastGen всё + мои лица" }));
    expect(screen.getByText(/будет отправлено до 3 визуальных референсов/)).toBeTruthy();
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
      { indices: [], productionItemIds: ["production:ormuz"], provider: "agent" },
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
        productionItemIds: ["production:ormuz"],
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

  it("requires an explicit terminal provider failure before a new paid retry", () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      covers: [{
        production_item_id: "production:failed", title: "Failed", image_prompt: "same",
        status: "Требуется создать заново FastGen", accepted_generation_id: "generation-1",
        provider_generation_status: "failed", paths: [],
      }],
    };
    render(<Covers data={data} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Выбрать: Failed" }));
    const retry = screen.getByRole("button", { name: "Создать новый платный запрос" });
    expect(retry.hasAttribute("disabled")).toBe(false);
    fireEvent.click(retry);
    expect(command).toHaveBeenCalledWith("retry-cover-generation-new-paid", {
      indices: [0], productionItemIds: ["production:failed"],
    });
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

  it("repeats current selected covers with their saved render contract", () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      covers: [{
        production_item_id: "production:current",
        title: "Current",
        image_prompt: "saved semantic prompt",
        final_provider_prompt: "SAVED FINAL PROMPT",
        final_provider_prompt_options: ["SAVED FINAL PROMPT"],
        render_profile: {
          build_mode: "fastgen-full-my-face" as const,
          face_mode: "auto",
          text_mode: "fastgen" as const,
          local_face_only: false,
          operation: "saved_reference_operation",
        },
        paths: ["current.png"],
      }],
    };
    render(<Covers data={data} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Выбрать: Current" }));
    fireEvent.click(screen.getByRole("button", { name: "Настроить студию" }));
    expect(screen.getByText(/«Повторить текущие» всегда использует модель/)).toBeTruthy();
    expect(screen.getByText(/сохранённые у самой обложки/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Повторить текущие выбранных" }));

    expect(command).toHaveBeenCalledWith("regenerate-covers", {
      indices: [0],
      productionItemIds: ["production:current"],
      currentProfile: true,
    });
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

  it("keeps manual text explicit until the operator submits a manual save", async () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      covers: [{
        production_item_id: "production:manual",
        title: "Кремль меняет тон переговоров",
        image_prompt: "Negotiation scene",
        cover_headline: "РУЧНОЙ ЗАГОЛОВОК",
        headline_source: "MANUAL" as const,
        cover_subheadline: "Ручная вторая строка",
        subheadline_source: "MANUAL" as const,
        paths: [],
      }],
    };
    render(<Covers data={data} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "1. Кремль меняет тон переговоров" }));
    expect(screen.getAllByText("Вручную · сохранено")).toHaveLength(2);

    const headline = screen.getByRole("textbox", { name: /Заголовок на обложке/ });
    fireEvent.change(headline, { target: { value: "НОВЫЙ РУЧНОЙ ЗАГОЛОВОК" } });
    fireEvent.submit(headline.closest("form")!);
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-cover-headline", {
      index: 0,
      productionItemId: "production:manual",
      headline: "НОВЫЙ РУЧНОЙ ЗАГОЛОВОК",
    }));

  });

  it("saves an edited visual prompt against the inspected ProductionItem ID", async () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      covers: [{
        production_item_id: "production:manual-prompt",
        title: "Ручной visual prompt",
        image_prompt: "Old visual prompt",
        paths: [],
      }],
    };
    render(<Covers data={data} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "1. Ручной visual prompt" }));
    const prompt = screen.getByRole("textbox", { name: /Визуальный промпт для обложки/ });
    fireEvent.change(prompt, { target: { value: "Edited visual prompt" } });
    fireEvent.submit(prompt.closest("form")!);

    await waitFor(() => expect(command).toHaveBeenCalledWith("save-cover-manual-prompt", {
      productionItemId: "production:manual-prompt",
      prompt: "Edited visual prompt",
    }));
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

  it("shows the non-blocking zero-PNG fallback for my-faces generation", () => {
    const data = {
      ...fallback,
      covers: [{
        production_item_id: "item-no-face",
        title: "Переговоры без подходящего портрета",
        image_prompt: "Negotiation scene",
        faceSelectionMode: "prepared-reference" as const,
        faceSelectionReason: "no confident prepared face-tree match; continued without PNG",
        face_reference_count: 0,
        render_profile: { build_mode: "fastgen-full-my-face", text_mode: "fastgen" },
        paths: [],
      }],
    };
    render(<Covers data={data} command={vi.fn(async () => undefined)} />);

    fireEvent.keyDown(screen.getAllByRole("row")[1], { key: "Enter" });
    expect(screen.getByText("PNG лица в FastGen")).toBeTruthy();
    expect(screen.getByText("0 · no confident prepared face-tree match; continued without PNG")).toBeTruthy();
    expect(screen.getByText("fastgen-full-my-face")).toBeTruthy();
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

  it("routes Gallery repeat-with-new-prompts through a new render contract", () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      covers: [{
        production_item_id: "production:new",
        title: "Новый промпт",
        image_prompt: "fresh scene prompt",
        status: "Новые промпты созданы",
        paths: ["new.png"],
      }],
      coverSettings: {
        ...fallback.coverSettings,
        operation: "new_operation",
        buildMode: "fastgen-full-my-face" as const,
      },
    };
    render(<CoverGallery data={data} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "1. Новый промпт" }));
    fireEvent.click(
      screen.getByTitle("Клик — увеличить; Ctrl+клик — выбрать несколько"),
      { ctrlKey: true },
    );
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    fireEvent.click(screen.getByRole("button", { name: "Повторить с новыми (1)" }));

    expect(command).toHaveBeenCalledWith("regenerate-covers", {
      indices: [0],
      productionItemIds: ["production:new"],
      currentProfile: false,
      useBuildModeRanges: true,
      operation: "new_operation",
      buildMode: "fastgen-full-my-face",
      faceMode: "auto",
      textMode: "fastgen",
      localFaceOnly: false,
    });

    command.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Повторить текущие (1)" }));
    expect(command).toHaveBeenCalledWith("regenerate-covers", {
      indices: [0],
      productionItemIds: ["production:new"],
      currentProfile: true,
      operation: "new_operation",
    });
  });

  it("uses a new render contract for the inspector action labelled repeat-with-new", () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      covers: [{
        production_item_id: "production:inspector-new",
        title: "Новый промпт инспектора",
        image_prompt: "fresh inspector scene",
        status: "Новые промпты созданы",
        paths: [],
      }],
      coverSettings: {
        ...fallback.coverSettings,
        operation: "inspector_operation",
        buildMode: "fastgen-full" as const,
      },
    };
    render(<CoverGallery data={data} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "1. Новый промпт инспектора" }));
    fireEvent.click(screen.getByRole("button", { name: "Повторить с новыми" }));

    expect(command).toHaveBeenCalledWith("regenerate-covers", {
      indices: [0],
      productionItemIds: ["production:inspector-new"],
      currentProfile: false,
      useBuildModeRanges: true,
      operation: "inspector_operation",
      buildMode: "fastgen-full",
      faceMode: "auto",
      textMode: "fastgen",
      localFaceOnly: false,
    });
    expect(command).not.toHaveBeenCalledWith(
      "regenerate-covers",
      expect.objectContaining({ currentProfile: true }),
    );
  });

  it("keeps the inspector current-repeat action on its immutable saved contract", () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      covers: [{
        production_item_id: "production:inspector-current",
        title: "Текущая обложка инспектора",
        image_prompt: "saved inspector scene",
        status: "Готово",
        paths: [],
      }],
      coverSettings: {
        ...fallback.coverSettings,
        operation: "current_operation",
      },
    };
    render(<CoverGallery data={data} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "1. Текущая обложка инспектора" }));
    fireEvent.click(screen.getByRole("button", { name: "Повторить текущий" }));

    expect(command).toHaveBeenCalledWith("regenerate-covers", {
      indices: [0],
      productionItemIds: ["production:inspector-current"],
      currentProfile: true,
      operation: "current_operation",
    });
  });

  it("sends only new-prompt gallery topics through the new contract without clearing a manual face", () => {
    const command = vi.fn(async () => undefined);
    const data = {
      ...fallback,
      covers: [
        {
          production_item_id: "production:new-manual-face",
          title: "Новая обложка с выбранным лицом",
          image_prompt: "new political scene",
          status: "Новые промпты созданы",
          face_reference_source: "manual" as const,
          face_reference_label: "Ильхам Алиев",
          face_reference_path: "C:/faces/aliyev.png",
          paths: ["new.png"],
        },
        {
          production_item_id: "production:old-prompt",
          title: "Старая готовая обложка",
          image_prompt: "saved scene",
          status: "Готово",
          paths: ["old.png"],
        },
      ],
      coverSettings: {
        ...fallback.coverSettings,
        operation: "fresh_operation",
        buildMode: "fastgen-full-my-face" as const,
      },
    };
    render(<CoverGallery data={data} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "1. Новая обложка с выбранным лицом" }));
    fireEvent.click(screen.getByTitle("Клик — увеличить; Ctrl+клик — выбрать несколько"), { ctrlKey: true });
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    fireEvent.click(screen.getByRole("button", { name: "2. Старая готовая обложка" }));
    fireEvent.click(screen.getByTitle("Клик — увеличить; Ctrl+клик — выбрать несколько"), { ctrlKey: true });
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    fireEvent.click(screen.getByRole("button", { name: "Повторить с новыми (1)" }));

    expect(command).toHaveBeenCalledWith("regenerate-covers", {
      indices: [0],
      productionItemIds: ["production:new-manual-face"],
      currentProfile: false,
      useBuildModeRanges: true,
      operation: "fresh_operation",
      buildMode: "fastgen-full-my-face",
      faceMode: "auto",
      textMode: "fastgen",
      localFaceOnly: false,
    });
    expect(command).not.toHaveBeenCalledWith("clear-cover-face", expect.anything());
    expect(command).not.toHaveBeenCalledWith("select-cover-face-person", expect.anything());
    expect(data.covers[0].face_reference_source).toBe("manual");
    expect(data.covers[0].face_reference_label).toBe("Ильхам Алиев");
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
