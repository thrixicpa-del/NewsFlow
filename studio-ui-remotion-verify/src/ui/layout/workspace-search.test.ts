import { describe, expect, it } from "vitest";
import { buildWorkspaceSearchItems } from "./workspace-search";

describe("buildWorkspaceSearchItems", () => {
  it("indexes current snapshot objects without creating a parallel data store", () => {
    const items = buildWorkspaceSearchItems({
      ideaTopics: ["Ормуз на грани"],
      ideaProductionItems: [{ title: "Ормуз: нефтяной шок", direction: "news", topic: "Ормуз", angle: "рынок" }],
      scenarios: [{ index: 2, title: "Сценарий Ормуз", state: "Готово", result: "", error: "" }],
      covers: [{ title: "Обложка Ормуз", status: "Готово" }],
      voiceItems: [{ index: 2, title: "MP3 Ормуз", state: "Готово", path: "D:/voice.mp3" }],
      montageTasks: [{ index: 2, title: "Монтаж Ормуз", status: "Готово" }],
      publication: { v2: { queue: [], receipts: { receipt1: { title: "Публикация Ормуз", productionItemId: "p1" } } } },
    } as unknown as NewsFlowSnapshot);

    expect(items.map((item) => [item.kind, item.title, item.page])).toEqual(expect.arrayContaining([
      ["Topic", "Ормуз на грани", "ideas"],
      ["Script", "Сценарий Ормуз", "scripts"],
      ["MP3", "MP3 Ормуз", "audio"],
      ["Cover", "Обложка Ормуз", "coverGallery"],
      ["Montage", "Монтаж Ормуз", "editor"],
      ["Publication receipt", "Публикация Ормуз", "publication"],
    ]));
  });
});
