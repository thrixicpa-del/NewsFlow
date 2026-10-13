import { act, render, screen } from "@testing-library/react";
import { Cutter, fallback, Footage } from "../../App";
import { describe, expect, it, vi } from "vitest";

describe("Media ingest workspaces", () => {
  it("shows media quarantine separately from screen-text exclusions", () => {
    const data = {
      ...fallback, footageFolders: ["D:/isolated-footage"],
      footageIndex: {
        ...fallback.footageIndex, mediaQuarantined: 3, englishBlocked: 82,
        mediaQuarantine: [{ path: "D:/isolated-footage/bad.mp4", reason: "moov atom not found" }],
      },
    };
    render(<Footage data={data} command={vi.fn()} refresh={async () => undefined} />);
    expect(screen.getByText(/Карантин повреждённых видео: 3/)).toBeTruthy();
    expect(screen.getByText(/Исключено английских надписей: 82/)).toBeTruthy();
    expect(screen.getByText(/Карантин повреждённых видео: 3/).getAttribute("title")).toContain("moov atom not found");
  });

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

  it("starts only one footage index command after rapid repeated clicks", () => {
    const command = vi.fn(() => new Promise<undefined>(() => undefined));
    render(
      <Footage
        data={{ ...fallback, footageFolders: ["D:/isolated-footage"] }}
        command={command}
        refresh={async () => undefined}
      />,
    );

    const button = screen.getByRole("button", { name: "ИИ-индексация" });
    act(() => {
      button.click();
      button.click();
    });

    expect(command).toHaveBeenCalledTimes(1);
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });

  it("exposes proxy warm-up progress from the existing footage roots", () => {
    const command = vi.fn().mockResolvedValue(undefined);
    render(
      <Footage
        data={{
          ...fallback,
          footageFolders: ["D:/isolated-footage"],
          proxyCache: {
            status: {
              stage: "warming",
              active: true,
              total: 10,
              processed: 4,
              ready: 3,
              skipped: 1,
              excluded: 2,
              failed: 0,
              current: "clip-004.mp4",
            },
          },
        }}
        command={command}
        refresh={async () => undefined}
      />,
    );

    expect(screen.getByText(/готово: 3/i)).toBeTruthy();
    expect(screen.getByText(/осталось: 6/i)).toBeTruthy();
    const button = screen.getByRole("button", { name: "Подготовить proxy-кэш" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });

  it("starts one proxy warm-up from the existing footage roots", async () => {
    const command = vi.fn().mockResolvedValue(undefined);
    render(
      <Footage
        data={{ ...fallback, footageFolders: ["D:/isolated-footage"] }}
        command={command}
        refresh={async () => undefined}
      />,
    );

    const button = screen.getByRole("button", { name: "Подготовить proxy-кэш" });
    await act(async () => {
      button.click();
      button.click();
    });
    expect(command).toHaveBeenCalledWith("run-proxy-cache-warmup", {});
    expect(command).toHaveBeenCalledTimes(1);
  });

  it("shows an interrupted proxy run as restartable, not as a live pause", () => {
    const command = vi.fn().mockResolvedValue(undefined);
    render(
      <Footage
        data={{
          ...fallback,
          footageFolders: ["D:/isolated-footage"],
          proxyCache: {
            status: {
              stage: "interrupted",
              active: false,
              pauseRequested: false,
              total: 10,
              processed: 4,
              message: "Подготовка proxy прервана. Запустите её снова.",
            },
          },
        }}
        command={command}
        refresh={async () => undefined}
      />,
    );

    expect(screen.getByRole("button", { name: "Продолжить подготовку" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Продолжить" })).toBeNull();
    expect(screen.getByText(/подготовка proxy-кэша прервана/i)).toBeTruthy();
  });

  it("requests a safe proxy pause without changing footage roots", async () => {
    const command = vi.fn().mockResolvedValue(undefined);
    render(
      <Footage
        data={{
          ...fallback,
          footageFolders: ["D:/isolated-footage"],
          proxyCache: { status: { stage: "warming", active: true, total: 10, processed: 4 } },
        }}
        command={command}
        refresh={async () => undefined}
      />,
    );

    await act(async () => screen.getByRole("button", { name: "Пауза" }).click());

    expect(command).toHaveBeenCalledWith("set-proxy-cache-paused", { paused: true });
  });

  it("classifies persisted English/Latin verdicts without starting a media rescan", async () => {
    const command = vi.fn().mockResolvedValue({
      indexResult: {
        total: 5,
        processed: 5,
        indexed: 5,
        skipped: 0,
        failed: 0,
        screenText: { checked: 5, blocked: 2, safe: 3, uncertain: 0 },
      },
    });
    render(
      <Footage
        data={{
          ...fallback,
          footageFolders: ["D:/isolated-footage"],
          footageIndex: { ...fallback.footageIndex, indexed: 5, total: 5, englishUnchecked: 5 },
        }}
        command={command}
        refresh={async () => undefined}
      />,
    );

    await act(async () => {
      screen.getByRole("button", { name: "Проверить English/Latin текст" }).click();
    });

    expect(command).toHaveBeenCalledWith("index-footage", { screenText: true });
    expect(await screen.findByText(/Проверка English\/Latin текста завершена/i)).toBeTruthy();
  });

  it("does not describe an unavailable local text model as an up-to-date check", async () => {
    const command = vi.fn().mockResolvedValue({
      indexResult: {
        total: 5,
        processed: 0,
        indexed: 0,
        skipped: 0,
        failed: 0,
        screenText: { checked: 0, blocked: 0, safe: 0, uncertain: 5, modelReady: false },
      },
    });
    render(
      <Footage
        data={{
          ...fallback,
          footageFolders: ["D:/isolated-footage"],
          footageIndex: { ...fallback.footageIndex, indexed: 5, total: 5, englishUnchecked: 5 },
        }}
        command={command}
        refresh={async () => undefined}
      />,
    );

    await act(async () => {
      screen.getByRole("button", { name: "Проверить English/Latin текст" }).click();
    });

    expect(await screen.findByText(/Локальная text-модель недоступна/i)).toBeTruthy();
  });

  it("shows truthful screen-text maintenance progress instead of the full base-index count", () => {
    render(
      <Footage
        data={{
          ...fallback,
          footageFolders: ["D:/isolated-footage"],
          footageIndex: {
            ...fallback.footageIndex,
            indexed: 27797,
            total: 27797,
            englishUnchecked: 5,
            status: {
              stage: "screen-text",
              active: true,
              total: 5,
              processed: 2,
              indexed: 2,
              failed: 0,
              current: "clip-2.mp4",
            },
          },
        }}
        command={vi.fn()}
        refresh={async () => undefined}
      />,
    );

    expect(screen.getByText(/прочитано: 2 из 5 · осталось: 3 · 40%/i)).toBeTruthy();
  });

  it("shows interrupted progress and truthful resumable counts", () => {
    render(
      <Footage
        data={{
          ...fallback,
          footageFolders: ["D:/isolated-footage"],
          footageIndex: {
            ...fallback.footageIndex,
            indexed: 2,
            total: 8,
            englishBlocked: 1,
            englishSafe: 1,
            englishUnchecked: 0,
            status: {
              stage: "paused",
              active: false,
              total: 8,
              processed: 3,
              indexed: 2,
              failed: 1,
              message: "Индексация прервана. Продолжите её.",
            },
          },
        }}
        command={vi.fn()}
        refresh={async () => undefined}
      />,
    );

    expect(screen.getByRole("button", { name: "Продолжить индексацию" })).toBeTruthy();
    expect(screen.getByText(/прочитано: 3 из 8 · осталось: 5 · 38%/i)).toBeTruthy();
    expect(screen.getByText("Индексация прервана. Продолжите её.")).toBeTruthy();
  });

  it("distinguishes a ready base index from an outdated deep semantic tier", () => {
    render(
      <Footage
        data={{
          ...fallback,
          footageFolders: ["D:/isolated-footage"],
          footageIndex: {
            ...fallback.footageIndex,
            indexed: 8,
            total: 8,
            semanticCurrent: 5,
            semanticOutdated: 3,
            semanticVersion: 5,
          },
        }}
        command={vi.fn()}
        refresh={async () => undefined}
      />,
    );

    expect(screen.getByText("Базовый индекс готов: 8 клипов.")).toBeTruthy();
    expect(screen.getByText("Требуется глубокое обновление: 3 клипа (версия 5).")).toBeTruthy();
  });
});
