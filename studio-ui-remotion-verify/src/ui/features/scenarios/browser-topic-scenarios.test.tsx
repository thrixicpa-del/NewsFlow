import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BrowserTopicScenarios, fallback } from "../../App";

describe("browser topic scenarios", () => {
  it("saves and launches selected topics by durable ProductionItem IDs, never previous prose", async () => {
    const data = {
      ...fallback,
      chromeSessions: [{ id: "chatgpt-isolated", label: "ChatGPT isolated", active: true, limitStatus: "available", usage: { ideas: false, scenarios: true, covers: false, seo: false } }],
      browserTopicScenarios: {
        ...fallback.browserTopicScenarios,
        projectUrl: "https://chatgpt.com/g/project",
        sessionId: "chatgpt-isolated",
        companionPrompt: "Только готовый текст.",
      },
      scenarios: [{
        index: 4,
        productionItemId: "production-immutable-4",
        title: "Тема из очереди",
        state: "Ожидает",
        result: "Старый сценарий не должен оказаться в browser prompt.",
        error: "",
      }],
    };
    const command = vi.fn(async () => data);
    render(<BrowserTopicScenarios data={data} command={command} />);

    expect(screen.getByText("Тема из очереди")).toBeTruthy();
    expect(screen.queryByText("Старый сценарий не должен оказаться в browser prompt.")).toBeNull();
    fireEvent.click(screen.getByLabelText("Выбрать: Тема из очереди"));
    fireEvent.click(screen.getByRole("button", { name: "Создать сценарии в ChatGPT" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "generate-browser-topic-scenarios",
      { indices: [4], productionItemIds: ["production-immutable-4"] },
    ));
    expect(command).toHaveBeenCalledWith("save-browser-topic-scenario-settings", expect.objectContaining({
      projectUrl: "https://chatgpt.com/g/project",
      sessionId: "chatgpt-isolated",
    }));
  });
});
