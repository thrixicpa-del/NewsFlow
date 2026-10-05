import { describe, expect, it } from "vitest";
import { coreAvailabilityNotice } from "./core-availability";

describe("Core availability notice", () => {
  it("explains a legacy stdout buffer failure without exposing raw diagnostics", () => {
    const message = coreAvailabilityNotice(new Error("stdout maxBuffer length exceeded: api-key=never-show"));

    expect(message).toContain("объём снимка проекта");
    expect(message).toContain("Данные проекта не удалены");
    expect(message).not.toContain("api-key");
  });

  it("distinguishes missing and failed-to-launch Core from a generic snapshot failure", () => {
    expect(coreAvailabilityNotice(new Error("Ядро NewsFlow не найдено в этой сборке.")))
      .toContain("не найдено");
    const launch = coreAvailabilityNotice(new Error("NewsFlow не смог запустить ядро: нет доступа к файлу Core."));
    expect(launch).toContain("не удалось запустить");
    expect(launch).toContain("Данные проекта не удалены");
    expect(coreAvailabilityNotice(new Error("unexpected low-level diagnostic")))
      .toContain("не удалось получить снимок");
  });
});
