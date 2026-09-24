import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { fallback, Ideas } from "../../App";

describe("Ideas Light view", () => {
  it("uses a compact editorial table and opens generation controls in a Sheet", () => {
    render(<Ideas data={fallback} go={vi.fn()} command={vi.fn()} />);

    expect(screen.getByRole("table", { name: "Избранные направления" })).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Настроить генерацию" }));
    expect(screen.getByRole("dialog", { name: "Маршрут генерации" })).not.toBeNull();
    expect(screen.getByLabelText("Требования к генерации")).not.toBeNull();
  });

  it("keeps the existing add-to-plan and generation command contracts", () => {
    const command = vi.fn();
    render(<Ideas data={fallback} go={vi.fn()} command={command} />);

    expect(screen.getByLabelText("Editorial Workspace")).not.toBeNull();
    const topic = fallback.ideaTopics[0];
    fireEvent.click(screen.getByRole("button", { name: topic }));
    fireEvent.click(screen.getByRole("button", { name: "Добавить в план" }));
    fireEvent.click(screen.getByRole("button", { name: "Сгенерировать идеи" }));

    expect(screen.getByLabelText("Новая тема")).not.toBeNull();
    expect(screen.getByLabelText("Векторов для выбранных направлений")).not.toBeNull();
    expect(command).toHaveBeenCalledWith("add-topics-to-plan", {
      topics: [topic], count: 5, provider: "agent", requirements: "",
    });
    expect(command).toHaveBeenCalledWith("generate-ideas", {
      topics: [topic], count: 5, provider: "agent", requirements: "",
    });
  });

  it("shows a running state and a visible proposal summary after generation", async () => {
    let resolve!: (value: typeof fallback) => void;
    const command = vi.fn(() => new Promise<typeof fallback>((done) => { resolve = done; }));
    render(<Ideas data={{ ...fallback, ideaPlan: [{ topic: "Направление", count: 2, provider: "agent" }] }} go={vi.fn()} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "Сгенерировать идеи" }));
    expect(screen.getByRole("button", { name: "Генерация идей…" })).not.toBeNull();
    expect(screen.getByText("Идёт генерация заголовков…")).not.toBeNull();

    resolve({
      ...fallback,
      ideaPlan: [{ topic: "Направление", count: 2, provider: "agent" }],
      ideaSuggestedTopics: ["Заголовок для research"],
      operationResult: {
        kind: "ideas", count: 1,
        message: "Сгенерировано: 1. Предложений: 1. На research: 1. Отклонено: 0.",
        generation: { generated: 1, suggested: 1, needsResearch: 1, rejected: 0 },
      },
    });

    await waitFor(() => expect(screen.getByRole("button", { name: "Сгенерировать идеи" })).not.toBeNull());
    expect(screen.getByText(/Сгенерировано: 1/)).not.toBeNull();
  });

  it("does not submit suggest-topics twice while the current command is running", () => {
    const command = vi.fn(() => new Promise<typeof fallback>(() => {}));
    render(<Ideas data={fallback} go={vi.fn()} command={command} />);

    const suggest = screen.getByRole("button", { name: "Агент предложит направления" });
    fireEvent.click(suggest);
    fireEvent.click(suggest);

    expect(command).toHaveBeenCalledTimes(1);
    expect(suggest).toHaveProperty("disabled", true);
  });

  it("does not submit reference-channel analysis twice while the current command is running", () => {
    const command = vi.fn(() => new Promise<typeof fallback>(() => {}));
    render(<Ideas data={fallback} go={vi.fn()} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "Каналы-референсы" }));
    const analyze = screen.getByRole("button", { name: "Найти залетевшие и проанализировать" });
    fireEvent.click(analyze);
    fireEvent.click(analyze);

    expect(command).toHaveBeenCalledTimes(1);
    expect(analyze).toHaveProperty("disabled", true);
  });

  it("does not submit YouTube research twice while the current command is running", () => {
    const command = vi.fn(() => new Promise<typeof fallback>(() => {}));
    render(<Ideas data={fallback} go={vi.fn()} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "YouTube-темы" }));
    fireEvent.change(screen.getByLabelText("Ключевые слова для YouTube"), {
      target: { value: "Ормуз нефть танкеры" },
    });
    const research = screen.getByRole("button", { name: "Найти темы" });
    fireEvent.click(research);
    fireEvent.click(research);

    expect(command).toHaveBeenCalledTimes(1);
    expect(research).toHaveProperty("disabled", true);
  });

  it("adds a manually entered topic through the current add-topic command", () => {
    const command = vi.fn().mockResolvedValue(fallback);
    render(<Ideas data={fallback} go={vi.fn()} command={command} />);

    fireEvent.change(screen.getByLabelText("Новая тема"), {
      target: { value: "Проверочная тема" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Добавить тему" }));

    expect(command).toHaveBeenCalledWith("add-topic", { topic: "Проверочная тема" });
  });

  it("keeps the main suggestion approval command contract", async () => {
    const suggestion = "Предложение агента";
    const command = vi.fn().mockResolvedValue(fallback);
    render(
      <Ideas
        data={{ ...fallback, ideaSuggestedTopics: [suggestion] }}
        go={vi.fn()}
        command={command}
      />,
    );

    fireEvent.click(screen.getByRole("checkbox", { name: `Выбрать предложение ${suggestion}` }));
    fireEvent.click(screen.getByRole("button", { name: "В избранные (1)" }));

    await waitFor(() =>
      expect(command).toHaveBeenCalledWith("add-suggested-topics-to-favorites", {
        topics: [suggestion],
      }),
    );
  });

  it("marks YouTube suggestion approval with its staging source", async () => {
    const suggestion = "YouTube предложение";
    const command = vi.fn().mockResolvedValue(fallback);
    render(
      <Ideas
        data={{ ...fallback, youtubeSuggestedTopics: [suggestion] }}
        go={vi.fn()}
        command={command}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "YouTube-темы" }));
    fireEvent.click(screen.getByRole("checkbox", { name: `Выбрать YouTube-предложение ${suggestion}` }));
    fireEvent.click(screen.getByRole("button", { name: "В избранные" }));

    await waitFor(() =>
      expect(command).toHaveBeenCalledWith("add-suggested-topics-to-favorites", {
        topics: [suggestion],
        source: "youtube",
      }),
    );
  });

  it("deletes only the checked topics through the current command after confirmation", () => {
    const command = vi.fn().mockResolvedValue(fallback);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<Ideas data={fallback} go={vi.fn()} command={command} />);

    const [first, second] = fallback.ideaTopics;
    fireEvent.click(screen.getByRole("checkbox", { name: `Выбрать ${first}` }));
    fireEvent.click(screen.getByRole("checkbox", { name: `Выбрать ${second}` }));
    fireEvent.click(screen.getByRole("button", { name: "Удалить выбранные темы" }));

    expect(confirm).toHaveBeenCalledOnce();
    expect(command).toHaveBeenCalledWith("delete-topics", { topics: [first, second] });
    confirm.mockRestore();
  });

  it("does not send a second selected-topic delete while the first is still running", () => {
    let resolve!: (value: typeof fallback) => void;
    const command = vi.fn(() => new Promise<typeof fallback>((done) => { resolve = done; }));
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<Ideas data={fallback} go={vi.fn()} command={command} />);

    const topic = fallback.ideaTopics[0];
    fireEvent.click(screen.getByRole("checkbox", { name: `Выбрать ${topic}` }));
    const remove = screen.getByRole("button", { name: "Удалить выбранные темы" });
    fireEvent.click(remove);
    fireEvent.click(remove);

    expect(command).toHaveBeenCalledTimes(1);
    resolve(fallback);
    confirm.mockRestore();
  });

  it("clears stale topic selection after a delete snapshot so the next action remains usable", () => {
    const command = vi.fn().mockResolvedValue(fallback);
    const topic = fallback.ideaTopics[0];
    const { rerender } = render(<Ideas data={fallback} go={vi.fn()} command={command} />);

    fireEvent.click(screen.getByRole("checkbox", { name: `Выбрать ${topic}` }));
    rerender(
      <Ideas
        data={{ ...fallback, ideaTopics: fallback.ideaTopics.slice(1) }}
        go={vi.fn()}
        command={command}
      />,
    );

    expect(screen.getByText("Не выбрано")).not.toBeNull();
    fireEvent.change(screen.getByLabelText("Новая тема"), { target: { value: "Новая после удаления" } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить тему" }));
    expect(command).toHaveBeenCalledWith("add-topic", { topic: "Новая после удаления" });
  });

  it("keeps generated proposals outside the release plan and rejects only checked proposals", async () => {
    const proposal = "Предложение для проверки";
    const command = vi.fn().mockResolvedValue({
      ...fallback,
      ideaSuggestedTopics: [proposal],
      ideaPlan: [{ topic: "Ручной план", count: 3, provider: "agent" }],
    });
    render(
      <Ideas
        data={{
          ...fallback,
          ideaSuggestedTopics: [proposal],
          ideaPlan: [{ topic: "Ручной план", count: 3, provider: "agent" }],
        }}
        go={vi.fn()}
        command={command}
      />,
    );

    expect(screen.getByText(/Не добавлены в избранные или план выпуска/)).not.toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: `Выбрать предложение ${proposal}` }));
    fireEvent.click(screen.getByRole("button", { name: "Отклонить выбранные" }));

    await waitFor(() =>
      expect(command).toHaveBeenCalledWith("reject-suggested-topics", { topics: [proposal] }),
    );
  });

  it("adds selected generated ideas to scenarios through the current command", async () => {
    const idea = "Идея для сценария";
    const command = vi.fn().mockResolvedValue({ ...fallback, ideaResults: [idea] });
    const go = vi.fn();
    render(<Ideas data={{ ...fallback, ideaResults: [idea] }} go={go} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: idea }));
    fireEvent.click(screen.getByRole("button", { name: "Добавить сценарии" }));

    await waitFor(() =>
      expect(command).toHaveBeenCalledWith("add-ideas-to-scenarios", { ideas: [idea] }),
    );
    expect(go).toHaveBeenCalledWith("scenarios");
  });

  it("sends the confirmed delete-all-production action through an in-app dialog", async () => {
    const command = vi.fn().mockResolvedValue(fallback);
    const onNotice = vi.fn();
    render(<Ideas data={fallback} go={vi.fn()} command={command} onNotice={onNotice} />);

    fireEvent.click(screen.getByRole("button", { name: "Удалить всё производство" }));
    expect(screen.getByRole("dialog", { name: "Удалить всё производство" })).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Контрольная фраза"), {
      target: { value: "УДАЛИТЬ ПРОИЗВОДСТВО" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить удаление" }));

    await waitFor(() =>
      expect(command).toHaveBeenCalledWith("clear-production-queue", {
        confirmed: true,
        confirmationPhrase: "УДАЛИТЬ ПРОИЗВОДСТВО",
      }),
    );
    expect(onNotice).toHaveBeenCalledWith("Производство удалено.");
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Удалить всё производство" })).toBeNull(),
    );
  });

  it("cancels delete-all-production in-app without calling the core", () => {
    const command = vi.fn();
    const onNotice = vi.fn();
    render(<Ideas data={fallback} go={vi.fn()} command={command} onNotice={onNotice} />);

    fireEvent.click(screen.getByRole("button", { name: "Удалить всё производство" }));
    fireEvent.click(screen.getByRole("button", { name: "Отмена" }));

    expect(command).not.toHaveBeenCalled();
    expect(onNotice).toHaveBeenCalledWith("Удаление производства отменено.");
    expect(screen.queryByRole("dialog", { name: "Удалить всё производство" })).toBeNull();
  });

  it("rejects a mismatched delete phrase without calling the core", () => {
    const command = vi.fn();
    const onNotice = vi.fn();
    render(<Ideas data={fallback} go={vi.fn()} command={command} onNotice={onNotice} />);

    fireEvent.click(screen.getByRole("button", { name: "Удалить всё производство" }));
    fireEvent.change(screen.getByLabelText("Контрольная фраза"), {
      target: { value: "удалить производство" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить удаление" }));

    expect(command).not.toHaveBeenCalled();
    expect(onNotice).toHaveBeenCalledWith(
      "Фраза подтверждения не совпадает. Производство не удалено.",
    );
    expect(screen.getByRole("dialog", { name: "Удалить всё производство" })).toBeTruthy();
  });

  it("submits confirmed delete-all-production only once while the current command is running", async () => {
    let resolve!: (value: typeof fallback) => void;
    const command = vi.fn(() => new Promise<typeof fallback>((done) => { resolve = done; }));
    const onNotice = vi.fn();
    render(<Ideas data={fallback} go={vi.fn()} command={command} onNotice={onNotice} />);

    fireEvent.click(screen.getByRole("button", { name: "Удалить всё производство" }));
    fireEvent.change(screen.getByLabelText("Контрольная фраза"), {
      target: { value: "УДАЛИТЬ ПРОИЗВОДСТВО" },
    });
    const submit = screen.getByRole("button", { name: "Подтвердить удаление" });
    fireEvent.click(submit);
    fireEvent.click(submit);

    expect(command).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Удаление производства…" })).toHaveProperty("disabled", true);
    resolve(fallback);
    await waitFor(() => expect(onNotice).toHaveBeenCalledWith("Производство удалено."));
  });

  it("does not render implementation diagnostics in the editorial workspace", () => {
    render(
      <Ideas
        data={{
          ...fallback,
          ideaRejectedItems: [{
            reason: "production_duplicate",
            candidate: { title: "Технический кандидат" },
            script_overlap: 0.8,
            event_bundle_overlap: 0.9,
            payload_overlap: 0.7,
          }],
        }}
        go={vi.fn()}
        command={vi.fn()}
      />,
    );

    expect(screen.queryByText(/Production duplicates/i)).toBeNull();
    expect(screen.queryByText(/event bundle/i)).toBeNull();
  });
});
