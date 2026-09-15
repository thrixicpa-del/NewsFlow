import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const studioRoot = resolve(import.meta.dirname, "../../..");

describe("design-system Storybook infrastructure", () => {
  it("documents source UI primitives with the project stylesheet", () => {
    const mainPath = resolve(studioRoot, ".storybook/main.ts");
    const previewPath = resolve(studioRoot, ".storybook/preview.ts");
    const tokensPath = resolve(studioRoot, "src/ui/components/design-tokens.css");

    expect(existsSync(mainPath)).toBe(true);
    expect(existsSync(previewPath)).toBe(true);
    expect(existsSync(tokensPath)).toBe(true);
    expect(readFileSync(mainPath, "utf8")).toContain("src/ui/**/*.stories");
    expect(readFileSync(previewPath, "utf8")).toContain("../src/ui/styles.css");
    expect(existsSync(resolve(studioRoot, "src/ui/components/workstation-components.stories.tsx"))).toBe(true);
  });
});
