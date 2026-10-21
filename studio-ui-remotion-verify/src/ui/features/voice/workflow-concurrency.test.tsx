import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { App, fallback } from "../../App";

afterEach(() => {
  cleanup();
  delete window.newsflowDesktop;
});

const state = {
  ...fallback,
  scenarios: [{ index: 0, title: "Synthetic", state: "Готово", result: "Text", error: "" }],
  voiceItems: [{ index: 0, title: "Synthetic", state: "Готово", path: "", voiceStatus: "В очереди" }],
};

async function openVoice() {
  if (!screen.queryByRole("button", { name: "Озвучка — очередь" })) {
    fireEvent.click(screen.getByRole("button", { name: "ПРОИЗВОДСТВО" }));
  }
  fireEvent.click(screen.getByRole("button", { name: "Озвучка — очередь" }));
  await screen.findByRole("button", { name: "1. Synthetic" });
}

it("explains a conflicting voice start and leaves the retry control available", async () => {
  const reason = "Очередь озвучки уже выполняется. Дождитесь завершения текущей очереди.";
  const command = vi.fn().mockRejectedValue(new Error(`Error invoking remote method 'newsflow:command': Error: ${reason}`));
  Object.defineProperty(window, "newsflowDesktop", { configurable: true,
    value: { snapshot: vi.fn().mockResolvedValue(state), command } });
  render(<App />);
  await openVoice();
  fireEvent.click(screen.getByRole("button", { name: "Озвучить всё" }));
  await screen.findByText(`Не выполнено: ${reason}`);
  expect(command).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button", { name: "Озвучить всё" }).hasAttribute("disabled")).toBe(false);
});

it("saves a template while voice is pending and retains both final results", async () => {
  let finishVoice: ((value: NewsFlowSnapshot) => void) | undefined;
  let latest = state;
  const command = vi.fn((name: string, payload: { template?: string }) => {
    if (name === "generate-voice-queue") return new Promise<NewsFlowSnapshot>((resolve) => { finishVoice = resolve; });
    if (name === "save-template") {
      latest = { ...latest, templateSettings: { ...latest.templateSettings, template: payload.template! } };
      return Promise.resolve(latest);
    }
    return Promise.resolve(latest);
  });
  Object.defineProperty(window, "newsflowDesktop", { configurable: true,
    value: { snapshot: vi.fn(async () => latest), command } });
  render(<App />);
  await openVoice();
  fireEvent.click(screen.getByRole("button", { name: "Озвучить всё" }));
  await waitFor(() => expect(finishVoice).toBeTypeOf("function"));
  if (!screen.queryByRole("button", { name: "Шаблоны" })) {
    fireEvent.click(screen.getByRole("button", { name: "ПОДГОТОВКА" }));
  }
  fireEvent.click(screen.getByRole("button", { name: "Шаблоны" }));
  fireEvent.change(screen.getByLabelText("Базовый шаблон сценария"), { target: { value: "New template {title}" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить шаблон" }));
  await screen.findByText("Все изменения сохранены");
  expect(command).toHaveBeenCalledWith("save-template", expect.objectContaining({ template: "New template {title}" }));
  await act(async () => { finishVoice?.({ ...latest,
    voiceItems: [{ ...state.voiceItems[0], path: "D:/test/voice.mp3", voiceStatus: "Готово" }] }); });
  expect((screen.getByLabelText("Базовый шаблон сценария") as HTMLTextAreaElement).value).toBe("New template {title}");
  await openVoice();
  expect(screen.getByText("voice.mp3")).toBeTruthy();
});
