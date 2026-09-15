import { describe, expect, it } from "vitest";
import { buildTaskCenterEntries } from "./task-model";

describe("buildTaskCenterEntries", () => {
  it("projects real backend states without treating a command acknowledgement as ready", () => {
    const entries = buildTaskCenterEntries({
      scenarios: [
        { index: 0, title: "Сценарий", state: "В обработке", result: "", error: "" },
        { index: 1, title: "Ошибка сценария", state: "Ошибка", result: "", error: "Нет ответа" },
      ],
      covers: [{ title: "Обложка", status: "Готово" }],
      voiceItems: [{ index: 0, title: "Озвучка", state: "В обработке", path: "", jobState: "running", voiceStatus: "Синтез" }],
      montageTasks: [{ index: 0, title: "Монтаж", status: "Пауза", progress: 42 }],
      publication: { v2: { queue: [{ snapshotId: "pub-1", productionItemId: "p-1", title: "Публикация", channelId: "channel", privacy: "private", publishMode: "publish_now", currentStage: "VIDEO_UPLOAD", status: "RETRYING", active: false, completion: { completed: 1, total: 5 }, steps: {} }] } },
    } as unknown as NewsFlowSnapshot);

    expect(entries.map((entry) => [entry.source, entry.status])).toEqual([
      ["scenario", "RUNNING"],
      ["scenario", "FAILED"],
      ["cover", "READY"],
      ["voice", "RUNNING"],
      ["montage", "PAUSED"],
      ["publication", "RETRYING"],
    ]);
    expect(entries.find((entry) => entry.source === "scenario" && entry.status === "FAILED")?.detail).toBe("Нет ответа");
  });

  it("keeps preparation and provider wait distinct from active execution", () => {
    const entries = buildTaskCenterEntries({
      scenarios: [{ index: 0, title: "План", state: "Планирование", result: "", error: "" }],
      covers: [{ title: "FastGen", status: "WAITING_FOR_PROVIDER" }],
      voiceItems: [], montageTasks: [], publication: { v2: { queue: [] } },
    } as unknown as NewsFlowSnapshot);

    expect(entries.map((entry) => entry.status)).toEqual(["PREPARING", "WAITING"]);
  });
});
