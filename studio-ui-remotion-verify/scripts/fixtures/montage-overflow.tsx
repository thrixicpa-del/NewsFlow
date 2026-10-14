import { createRoot } from "react-dom/client";
import { App, fallback } from "../../src/ui/App";

export const diagnostic = "FFmpeg/NVENC: D:/Исходные футажи/" + "длинный_Unicode_путь_🎬/".repeat(80) + "clip.mp4 SAR=13824:13825 frame=12345";
let state: NewsFlowSnapshot;

export function makeSnapshot(stage: string): NewsFlowSnapshot {
  const busy = stage !== "Ожидает" && stage !== "Готово";
  return {
    ...structuredClone(fallback),
    montageSettings: { ...fallback.montageSettings, queueRunning: true },
    scenarios: Array.from({ length: 4 }, (_, index) => ({ index, title: `Тестовая тема ${index + 1}`, state: "Готово", result: "Ручной сценарий", error: "" })),
    voiceItems: Array.from({ length: 4 }, (_, index) => ({ index, title: `Тестовая тема ${index + 1}`, state: "Готово", path: `D:/test/Озвучка ${index + 1}.mp3` })),
    montageProjects: stage === "Ожидает" ? [] : [{
      title: "Тестовая тема 1", path: `D:/test/${"длинная папка проекта/".repeat(8)}Тестовая тема 1.newsflow`, duration: 960,
      selectionSummaryText: "160 сцен · strict 156 · reuse 4",
      clips: Array.from({ length: 160 }, (_, index) => ({
        path: `D:/test/footage-${index + 1}.mp4`, duration: 6,
        narration: `Реплика ${index + 1} о событиях темы`, source: "local · STRICT_MATCH",
      })),
    }],
    montageTasks: Array.from({ length: 4 }, (_, index) => ({
      index, title: `Тестовая тема ${index + 1}`, status: stage === "Рендеринг" ? "Рендер" : stage,
      phase: busy ? `${stage}: ${diagnostic}` : stage, progress: stage === "Готово" ? 100 : busy ? 77 : 0,
      error: stage === "Ошибка" ? diagnostic : "", runtimeCurrent: true,
      outputPath: "", voicePath: `D:/test/Озвучка ${index + 1}.mp3`,
      timeline: busy || stage === "Готово" ? [{ at: "10:31:20", label: stage, detail: diagnostic, progress: 77 }] : [],
    })),
  };
}

export function setStage(stage: string) {
  state = makeSnapshot(stage);
}

export function install() {
  setStage("Ожидает");
  // The real App/Editor consumes snapshots; no Core or render command exists here.
  Object.defineProperty(window, "newsflowDesktop", { value: {
    snapshot: async () => structuredClone(state),
    command: async (name: string) => { throw new Error(`Unexpected command in layout-only test: ${name}`); },
  }, configurable: true });
  document.getElementById("root")?.remove();
  const host = document.createElement("div");
  host.id = "montage-layout-test-root";
  document.body.append(host);
  createRoot(host).render(<App />);
}
