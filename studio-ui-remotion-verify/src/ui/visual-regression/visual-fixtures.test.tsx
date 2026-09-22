import { Profiler, type ProfilerOnRenderCallback } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App, fallback } from "../App";
import { buildVisualFixture } from "./visual-fixtures";

describe("visual fixtures", () => {
  afterEach(() => {
    window.history.replaceState({}, "", "/");
    delete window.newsflowDesktop;
  });

  it("creates task states from a disposable snapshot without mutating the fallback", () => {
    const fixture = buildVisualFixture(fallback, "task-states");

    expect(fixture?.covers.some((cover) => cover.status === "FAILED")).toBe(true);
    expect(fixture?.voiceItems.some((item) => item.jobState === "WAITING_FOR_PROVIDER")).toBe(true);
    expect(fixture?.montageTasks.some((task) => task.status === "READY")).toBe(true);
    expect(fallback.covers).toEqual([]);
    expect(fallback.voiceItems).toEqual([]);
  });

  it("creates a disposable publication receipt without mutating the fallback", () => {
    const fixture = buildVisualFixture(fallback, "publication-receipt");

    expect(fixture?.publication.v2?.receipts).toMatchObject({
      "visual-receipt-1": expect.objectContaining({
        title: "Визуальный receipt публикации",
        productionItemId: "visual-production-1",
      }),
    });
    expect(fallback.publication.v2?.receipts || {}).toEqual({});
  });

  it("creates a ready SEO and Tags package without mutating the fallback", () => {
    const fixture = buildVisualFixture(fallback, "metadata-ready");

    expect(fixture?.seo).toEqual([
      expect.objectContaining({
        source_title: "Визуальная тема для metadata desk",
        status: "Готово",
        tags_status: "Готово",
      }),
    ]);
    expect(fallback.seo).toEqual([]);
  });

  it("creates a disposable configured channel for the OAuth handoff state", () => {
    const fixture = buildVisualFixture(fallback, "analytics-oauth-waiting");

    expect(fixture?.analyticsOAuth).toMatchObject({ configured: true, mode: "cloudflare" });
    expect(fixture?.channels).toEqual([expect.objectContaining({ name: "Визуальный канал OAuth", oauthConnected: false })]);
    expect(fallback.channels).toEqual([]);
    expect(fallback.analyticsOAuth.configured).toBe(false);
  });

  it("creates an 84-item active Cover fixture for the measured current production scale", () => {
    const fixture = buildVisualFixture(fallback, "covers-84");

    expect(fixture?.covers).toHaveLength(84);
    expect(fixture?.coverCounts.total).toBe(84);
    expect(fallback.covers).toEqual([]);
  });

  it("creates an 84-item Publication fixture with eight channels and ads states", () => {
    const fixture = buildVisualFixture(fallback, "publication-84");

    expect(Object.keys(fixture?.publication.v2?.items || {})).toHaveLength(84);
    expect(fixture?.channels).toHaveLength(8);
    expect(fixture?.publication.v2?.queue).toHaveLength(84);
    expect(fixture?.publication.v2?.queue.some((row: any) => row.ads?.mode === "AUTO+MANUAL")).toBe(true);
    expect(fixture?.publication.v2?.queue.some((row: any) => row.ads?.mode === "AUTO_ONLY")).toBe(true);
    expect(fixture?.publication.v2?.queue.some((row: any) => row.ads?.mode === "NONE")).toBe(true);
    expect(fallback.channels).toEqual([]);
  });

  it("creates 84-item Voice and Montage fixtures without changing the fallback", () => {
    const voice = buildVisualFixture(fallback, "voice-84");
    const montage = buildVisualFixture(fallback, "montage-84");

    expect(voice?.voiceItems).toHaveLength(84);
    expect(voice?.scenarios).toHaveLength(84);
    expect(montage?.montageTasks).toHaveLength(84);
    expect(montage?.voiceItems).toHaveLength(84);
    expect(fallback.voiceItems).toEqual([]);
    expect(fallback.montageTasks).toEqual([]);
  });

  it("renders a query-selected fixture without calling the desktop runtime", () => {
    window.history.replaceState({}, "", "?visual-fixture=task-states");
    render(<App />);

    expect(screen.getByText("Озвучка ожидает провайдера")).toBeTruthy();
  });

  it("blocks a fixture settings write before it can reach the desktop runtime", () => {
    const saveSettings = vi.fn();
    window.newsflowDesktop = { saveSettings } as unknown as Window["newsflowDesktop"];
    window.history.replaceState({}, "", "?visual-fixture=task-states");
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(saveSettings).not.toHaveBeenCalled();
    expect(screen.getByText("Visual fixture: команда не запускается.")).toBeTruthy();
  });

  it("closes the active inspector on Escape without changing the fixture queue", () => {
    window.history.replaceState({}, "", "?visual-fixture=task-states");
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Открыть задачу: Озвучка ожидает провайдера" }));
    expect(screen.getByLabelText("Контекстный инспектор").textContent).toContain("Озвучка ожидает провайдера");

    fireEvent.keyDown(window, { key: "Escape" });

    expect(screen.getByLabelText("Контекстный инспектор").textContent).toContain("Выберите задачу");
    expect(screen.getByText("Озвучка ожидает провайдера")).toBeTruthy();
  });

  it("clears a task inspector selection when the user changes workspace", () => {
    window.history.replaceState({}, "", "?visual-fixture=task-states");
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Открыть задачу: Озвучка ожидает провайдера" }));
    expect(screen.getByLabelText("Контекстный инспектор").textContent).toContain("Озвучка ожидает провайдера");

    fireEvent.click(screen.getByRole("button", { name: "Генерация идей" }));

    expect(screen.getByLabelText("Контекстный инспектор").textContent).toContain("Выберите задачу");
  });

  it("keeps React commit counts bounded when opening 84-row media workspaces", () => {
    const routes = [
      { fixture: "covers-84", group: "ОБЛОЖКИ И ГЕНЕРАЦИИ", navigation: "Обложки YouTube", title: "Обложки YouTube" },
      { fixture: "voice-84", group: "ПРОИЗВОДСТВО", navigation: "Озвучка — очередь", title: "Очередь озвучки" },
      { fixture: "montage-84", group: "ПРОИЗВОДСТВО", navigation: "Монтаж", title: "Монтаж" },
      { fixture: "publication-84", group: "ПУБЛИКАЦИЯ", navigation: "Публикация YouTube", title: "Публикация YouTube" },
    ] as const;

    for (const route of routes) {
      window.history.replaceState({}, "", `?visual-fixture=${route.fixture}`);
      const commits: string[] = [];
      const onRender: ProfilerOnRenderCallback = (_id, phase) => commits.push(phase);
      const view = render(<Profiler id={route.fixture} onRender={onRender}><App /></Profiler>);

      fireEvent.click(screen.getByRole("button", { name: route.group }));
      fireEvent.click(screen.getByRole("button", { name: route.navigation }));

      expect(screen.getByRole("heading", { name: route.title })).toBeTruthy();
      expect(commits).toHaveLength(5);
      view.unmount();
      window.history.replaceState({}, "", "/");
    }
  });
});
