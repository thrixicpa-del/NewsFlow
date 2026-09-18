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
      buildMode: "fastgen-text-local-face", faceMode: "with", textMode: "fastgen", localFaceOnly: true,
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

  it("opens a cover inspector with the table keyboard workflow", () => {
    const data = {
      ...fallback,
      covers: [{ production_item_id: "item-ormuz", title: "Ормуз", image_prompt: "Танкер в Ормузе", prompt_provider: "agent", paths: [] }],
    };
    render(<Covers data={data} command={vi.fn(async () => undefined)} />);

    fireEvent.keyDown(screen.getAllByRole("row")[1], { key: "Enter" });
    expect(screen.getByText("Инспектор обложки")).toBeTruthy();
    expect(screen.getByText("ProductionItem ID")).toBeTruthy();
    expect(screen.getByText("item-ormuz")).toBeTruthy();
    expect(screen.getByText("agent")).toBeTruthy();
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
