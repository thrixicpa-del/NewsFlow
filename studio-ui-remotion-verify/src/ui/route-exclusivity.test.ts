import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const appSource = readFileSync(resolve(process.cwd(), "src/ui/App.tsx"), "utf8");

describe("current workstation route exclusivity", () => {
  it("keeps Covers, Voice, Montage, Analytics and Publication on their current workstation implementations", () => {
    expect(appSource).toContain('workspace="Covers"');
    expect(appSource).toContain("<Covers data={data} command={command} />");
    expect(appSource).toContain('workspace="Voice"');
    expect(appSource).toContain("<VoiceQueue");
    expect(appSource).toContain('workspace="Montage"');
    expect(appSource).toContain("<Editor data={data} command={command} refresh={refresh} />");
    expect(appSource).toContain('workspace="Analytics"');
    expect(appSource).toContain("<AnalyticsDashboard data={data} command={command} />");
    expect(appSource).toContain('workspace="Publication"');
    expect(appSource).toContain("<PublicationPage data={data} command={command} />");
  });

  it("does not mount a legacy dashboard through normal App routing", () => {
    expect(appSource).not.toContain("<LegacyPublicationDashboard");
    expect(appSource).not.toContain("<LegacyPublicationDashboardSimple");
    expect(appSource).not.toContain("<LegacyAnalyticsDashboard");
  });
});
