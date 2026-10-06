import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BrowserTopicScenarios, fallback } from "../../App";

describe("browser topic scenarios", () => {
  it("resolves numbered range assignments to durable IDs before saving", async () => {
    const data = {
      ...fallback,
      browserTopicScenarios: { ...fallback.browserTopicScenarios, companionPrompt: "Общий текст." },
      scenarios: [{ index: 0, productionItemId: "prod-one", title: "Первая", state: "Ожидает", result: "", error: "" }, {
        index: 2, productionItemId: "prod-three", title: "Третья", state: "Ожидает", result: "", error: "",
      }],
    };
    const command = vi.fn(async () => data);
    render(<BrowserTopicScenarios data={data} command={command} />);

    expect(screen.getByText("1")).toBeTruthy();
    expect(screen.getByText("3")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Номера тем для диапазона"), { target: { value: "1, 3" } });
    fireEvent.change(screen.getAllByLabelText("Минимум символов")[1], { target: { value: "2000" } });
    fireEvent.change(screen.getAllByLabelText("Максимум символов")[1], { target: { value: "3000" } });
    fireEvent.change(screen.getByLabelText("Дополнительный prompt для диапазона"), { target: { value: "Только для выбранных." } });
    fireEvent.click(screen.getByRole("button", { name: "Применить диапазон" }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить настройки" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith("save-browser-topic-scenario-settings", expect.objectContaining({
      lengthOverrides: {
        "prod-one": { minimum_chars: 2000, maximum_chars: 3000 },
        "prod-three": { minimum_chars: 2000, maximum_chars: 3000 },
      },
      additionalPromptOverrides: { "prod-one": "Только для выбранных.", "prod-three": "Только для выбранных." },
    })));
  });

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
        result: "",
        error: "",
      }, {
        index: 5,
        productionItemId: "production-existing-5",
        title: "Тема с готовым текстом",
        state: "Ошибка",
        result: "Старый сценарий не должен оказаться в browser prompt.",
        error: "Старый технический статус",
      }],
    };
    const command = vi.fn(async () => data);
    render(<BrowserTopicScenarios data={data} command={command} />);

    expect(screen.getByText("Тема из очереди")).toBeTruthy();
    expect(screen.getByText("Тема с готовым текстом")).toBeTruthy();
    expect(screen.queryByText("Старый сценарий не должен оказаться в browser prompt.")).toBeNull();
    const existingCheckbox = screen.getByLabelText("Выбрать: Тема с готовым текстом") as HTMLInputElement;
    expect(existingCheckbox.disabled).toBe(true);

    fireEvent.click(screen.getByLabelText("Выбрать: Тема из очереди"));
    const runButton = screen.getByRole("button", { name: "Создать сценарии в ChatGPT" }) as HTMLButtonElement;
    await waitFor(() => expect(runButton.disabled).toBe(false));
    fireEvent.click(runButton);

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
