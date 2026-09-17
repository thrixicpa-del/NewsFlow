import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("workstation visual capture contract", () => {
  it("measures route navigation before waiting for screenshot animation settling", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );
    const settle = captureScript.indexOf("await waitForVisualSettle(window);");
    const navigationMeasurement = captureScript.indexOf(
      "const navigationMs = performance.now() - navigationStartedAt;",
    );

    expect(settle).toBeGreaterThan(-1);
    expect(navigationMeasurement).toBeGreaterThan(-1);
    expect(navigationMeasurement).toBeLessThan(settle);
  });

  it("waits for two identical compositor frames before comparing a visual baseline", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );

    expect(captureScript).toContain("async function captureStablePage(window)");
    expect(captureScript).toContain("let stableFrames = 0;");
    expect(captureScript).toContain("pixelDifference(currentImage.toBitmap(), previousImage.toBitmap()) === 0");
    expect(captureScript).toContain("const currentPng = await captureStablePage(window);");
  });

  it("can render the current OAuth handoff UI only through a disposable local adapter", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );

    expect(captureScript).toContain("async function installVisualOauthAdapter(window)");
    expect(captureScript).toContain("visual-oauth-waiting");
    expect(captureScript).toContain("startYoutubeOAuthHandoff");
  });

  it("reports the pixel bounds when a visual baseline fails", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );

    expect(captureScript).toContain("function pixelDifferenceDetails(left, right, width)");
    expect(captureScript).toContain("bounds ${details.bounds}");
  });

  it("force-closes the disposable capture window after an OAuth waiting-state capture", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );

    expect(captureScript).toContain("if (!window.isDestroyed()) window.destroy();");
    expect(captureScript).toContain("app.exit();");
  });

  it("waits for the disposable Vite process tree before terminating visual capture", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );
    const stopVite = captureScript.indexOf("async function stopDisposableVite(vite)");
    const awaitStop = captureScript.indexOf("await stopDisposableVite(vite);");
    const exit = captureScript.indexOf("app.exit();", awaitStop);

    expect(stopVite).toBeGreaterThan(-1);
    expect(awaitStop).toBeGreaterThan(stopVite);
    expect(exit).toBeGreaterThan(awaitStop);
    expect(captureScript).toContain('taskkill.exe');
  });

  it("clears disposable renderer preferences before loading each visual case", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );
    const clearPreferences = captureScript.indexOf("localStorage.clear()");
    const loadCase = captureScript.indexOf("await window.loadURL(url.href);");

    expect(clearPreferences).toBeGreaterThan(-1);
    expect(clearPreferences).toBeLessThan(loadCase);
  });

  it("includes the active SEO and Tags production desks in the isolated visual matrix", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );

    expect(captureScript).toContain('{ id: "seo-empty"');
    expect(captureScript).toContain('{ id: "tags-empty"');
  });

  it("covers ready metadata artifacts independently from empty-state workspaces", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );

    expect(captureScript).toContain('{ id: "seo-ready", fixture: "metadata-ready"');
    expect(captureScript).toContain('{ id: "tags-ready", fixture: "metadata-ready"');
  });

  it("covers every remaining active workstation route on disposable empty state", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );
    const requiredCases = [
      "scenarios-empty",
      "templates-empty",
      "agents-empty",
      "cover-gallery-empty",
      "media-empty",
      "footage-empty",
      "cutter-empty",
      "voice-profiles-empty",
      "audio-empty",
      "outputs-empty",
      "sessions-empty",
    ];

    for (const caseId of requiredCases) expect(captureScript).toContain(`id: "${caseId}"`);
  });

  it("loads approved baselines from versioned test assets while keeping captures disposable", () => {
    const captureScript = readFileSync(
      resolve(process.cwd(), "scripts", "capture-workstation-baselines.mjs"),
      "utf8",
    );

    expect(captureScript).toContain('"tests", "visual-baselines", "approved"');
    expect(captureScript).toContain('".artifacts", "workstation-visual-baselines"');
  });

});
