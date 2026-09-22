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

  it("declares a real narrow Topics viewport instead of relying on a scaled desktop capture", () => {
    const narrowTopics = workstationBaselineCases.find((item) => item.id === "topics-narrow");
    expect(narrowTopics).toMatchObject({ page: "ideas", dataRoot: "disposable", viewport: { width: 390, height: 844 } });
  });
});
