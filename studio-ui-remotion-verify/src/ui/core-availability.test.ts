import { describe, expect, it } from "vitest";
import { coreAvailabilityNotice } from "./core-availability";

describe("Core availability notice", () => {
  it("explains a legacy stdout buffer failure without exposing raw diagnostics", () => {
    const message = coreAvailabilityNotice(new Error("stdout maxBuffer length exceeded: api-key=never-show"));

    expect(message).toContain("объём снимка проекта");
    expect(message).toContain("Данные проекта не удалены");
    expect(message).not.toContain("api-key");
  });

  it("distinguishes a missing bundled Core from a generic unavailable snapshot", () => {
    expect(coreAvailabilityNotice(new Error("В сборке не найдено актуальное ядро NewsFlow")))
      .toContain("не найдено");
    expect(coreAvailabilityNotice(new Error("unexpected low-level diagnostic")))
      .toContain("не удалось получить снимок");
  });
});
