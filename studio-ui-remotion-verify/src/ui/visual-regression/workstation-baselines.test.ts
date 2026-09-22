import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { workstationBaselineCases } from "./workstation-baselines";

describe("workstation visual baseline matrix", () => {
  it("covers the required production workspaces without production data", () => {
    expect(workstationBaselineCases.map((item) => item.id)).toEqual([
      "dashboard-empty",
      "topics-empty",
      "topics-narrow",
      "scripts-empty",
      "covers-empty",
      "covers-failed",
      "covers-84",
      "covers-inspector",
      "covers-configuration",
      "voice-empty",
      "voice-waiting",
      "voice-84",
      "audio-inspector",
      "voice-provider-readiness",
      "montage-empty",
      "montage-ready",
      "montage-84",
      "montage-inspector",
      "montage-configuration",
      "publication-empty",
      "publication-paused",
      "publication-84",
      "publication-narrow",
      "publication-day-plan",
      "publication-queue-ads",
      "publication-receipt",
      "analytics-oauth-waiting",
      "sidebar-collapsed",
      "knowledge-empty",
      "keys-discard-dialog",
      "task-states-inspector",
    ]);
    expect(workstationBaselineCases.every((item) => item.dataRoot === "disposable")).toBe(true);
  });

  it("declares real narrow viewports instead of relying on scaled desktop captures", () => {
    const narrowTopics = workstationBaselineCases.find((item) => item.id === "topics-narrow");
    const narrowPublication = workstationBaselineCases.find((item) => item.id === "publication-narrow");
    expect(narrowTopics).toMatchObject({ page: "ideas", dataRoot: "disposable", viewport: { width: 390, height: 844 } });
    expect(narrowPublication).toMatchObject({ page: "publication", dataRoot: "disposable", fixture: "publication-84", viewport: { width: 390, height: 844 } });
  });

  it("requires an approved PNG for every release visual baseline case", () => {
    const approvedRoot = resolve(process.cwd(), "tests", "visual-baselines", "approved");
    const missing = workstationBaselineCases
      .filter((item) => !existsSync(resolve(approvedRoot, `${item.id}.png`)))
      .map((item) => item.id);
    expect(missing).toEqual([]);
  });
});
