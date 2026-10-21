import { describe, expect, it } from "vitest";
import { buildTaskCenterEntries } from "./task-model";

describe("buildTaskCenterEntries", () => {
  it.each([
    { voiceStatus: "VoiceGen: выполняется", expected: "RUNNING" },
    { voiceStatus: "VoiceGen: готовим задачу", expected: "PREPARING" },
    { voiceStatus: "API: сохраняем MP3", expected: "RUNNING" },
    { voiceStatus: "Скачиваем готовый MP3", expected: "RUNNING" },
    { voiceStatus: "VoiceGen: скачиваем MP3", expected: "RUNNING" },
    { voiceStatus: "Ожидаем готовый MP3", expected: "WAITING" },
    { voiceStatus: "Ожидаем кнопку скачивания в истории", expected: "WAITING" },
    { voiceStatus: "Ожидание ответа провайдера", expected: "WAITING" },
    { voiceStatus: "Ошибка озвучки", expected: "FAILED" },
    { voiceStatus: "", expected: "QUEUED" },
  ])("keeps script readiness separate from voice $expected", ({ voiceStatus, expected }) => {
    const entries = buildTaskCenterEntries({
      scenarios: [], covers: [], montageTasks: [], publication: { v2: { queue: [] } },
      voiceItems: [{ index: 0, title: "Voice", state: "Готово", path: "", jobState: "", voiceStatus }],
    } as unknown as NewsFlowSnapshot);
    expect(entries[0].status).toBe(expected);
    expect(entries[0].detail).toBe(voiceStatus || "Ожидает озвучки");
  });

  it.each([
    { path: "old.mp3", expected: "WAITING" },
    { path: "ready.mp3", jobState: "ready", expected: "READY" },
    { path: "old.mp3", voiceError: "Ошибка провайдера", expected: "FAILED" },
    { path: "old.mp3", jobState: "cancelled", expected: "CANCELLED" },
  ])("preserves canonical state and errors over legacy activity labels", ({ expected, ...voice }) => {
    const entries = buildTaskCenterEntries({
      scenarios: [], covers: [], montageTasks: [], publication: { v2: { queue: [] } },
      voiceItems: [{ index: 0, title: "Voice", state: "Готово", voiceStatus: "Ожидаем готовый MP3", ...voice }],
    } as unknown as NewsFlowSnapshot);
    expect(entries[0].status).toBe(expected);
  });

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
