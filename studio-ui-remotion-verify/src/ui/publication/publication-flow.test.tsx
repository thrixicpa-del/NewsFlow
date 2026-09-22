import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PublicationPage } from "./PublicationPage";

const base = {
  channels: [{ id: "channel-a", channel: "channel-a", name: "Первый канал", subscribers: "30 000", status: "Подключён", oauthConnected: true, monetaryAccess: true }],
  publication: { uploadConcurrency: 6, v2: {
    items: {
      "item-ready": { productionItemId: "item-ready", metadata: { title: "Готовый ролик" }, readiness: { state: "VIDEO_READY" }, artifacts: { video: { path: "D:/ready.mp4", exists: true } } },
      "item-uploaded": { productionItemId: "item-uploaded", metadata: { title: "Уже загруженный ролик" }, readiness: { state: "VIDEO_READY" }, artifacts: { video: { path: "D:/uploaded.mp4", exists: true } } },
    },
    queue: [
      { snapshotId: "snapshot-ready", productionItemId: "item-ready", title: "Готовый ролик", channelId: "channel-a", currentStage: "WAITING", status: "WAITING", active: false, completion: { completed: 0, total: 8 }, steps: {} },
      { snapshotId: "snapshot-uploaded", productionItemId: "item-uploaded", title: "Уже загруженный ролик", channelId: "channel-a", currentStage: "THUMBNAIL", status: "PARTIAL", active: false, youtubeVideoId: "yt-123", completion: { completed: 4, total: 8 }, steps: { VIDEO_UPLOAD: { status: "SUCCESS" }, THUMBNAIL: { status: "FAILED" } } },
    ], counters: {}, paused: false, uploadConcurrency: 6, channelRules: {}, assignments: {},
    rulePresets: [{ name: "Будни", rules: { "channel-a": { channelId: "channel-a", enabled: true, quota: 3, monetized: true, distributionStrategy: "balanced", privacy: "private", publishMode: "schedule", timezone: "Europe/Minsk", firstPublishAt: "2026-11-15T04:00:00+03:00", intervalMinutes: 15, allowedWeekdays: [0,1,2,3,4,5,6], publishWindowStart: "04:00", publishWindowEnd: "10:00", dailyCap: 8, minDurationSeconds: 0, maxDurationSeconds: 0, orderStart: 1, orderEnd: 20, automation: { upload: true, metadata: true, thumbnail: true, ads: true, post: true, cards: true, endScreen: true } } } }],
  } },
} as unknown as NewsFlowSnapshot;

describe("PublicationPage interactions", () => {
  it("opens compact channel settings with range and quarter-hour scheduling controls", () => {
    render(<PublicationPage data={base} command={vi.fn().mockResolvedValue(undefined)} />);
    fireEvent.click(screen.getByRole("tab", { name: "Каналы" }));
    expect(screen.getByRole("columnheader", { name: "Действия" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Действия канала Первый канал" }));
    expect(screen.getByText("Количество роликов")).toBeInTheDocument();
    expect(screen.getByLabelText("Ролики с №")).toBeInTheDocument();
    expect(screen.getByLabelText("Ролики по №")).toBeInTheDocument();
    expect(screen.getByLabelText("Первый выход канала")).toHaveAttribute("step", "900");
    expect(screen.getByLabelText("Окно публикации: начало")).toHaveAttribute("step", "900");
    expect(screen.getByText(/:00 \/ :15 \/ :30 \/ :45/)).toBeInTheDocument();
    expect(screen.getByText(/реклама тоже обязательна/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Добавить исключение" }));
    expect(screen.getByLabelText("Blackout начало 1")).toHaveAttribute("step", "900");
    expect(screen.getByLabelText("Blackout конец 1")).toHaveAttribute("step", "900");
    expect(screen.getByLabelText("Blackout причина 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Сохранить" })).toBeInTheDocument();
  });

  it("applies and saves named channel-rule presets through the command contract", async () => {
    const command = vi.fn().mockResolvedValue(base);
    render(<PublicationPage data={base} command={command} />);
    fireEvent.click(screen.getByRole("tab", { name: "Каналы" }));

    fireEvent.change(screen.getByLabelText("Пресет правил каналов"), { target: { value: "Будни" } });
    fireEvent.click(screen.getByRole("button", { name: "Применить" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("apply-publication-v2-rule-preset", { name: "Будни" }));

    fireEvent.change(screen.getByLabelText("Название нового пресета"), { target: { value: "Мой план" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить текущие" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "save-publication-v2-rule-preset",
      expect.objectContaining({ name: "Мой план" }),
    ));
  });

  it("lets the operator set item priority and any IANA channel timezone", async () => {
    const command = vi.fn().mockResolvedValue(base);
    render(<PublicationPage data={base} command={command} />);

    fireEvent.change(screen.getByLabelText("Приоритет Готовый ролик"), { target: { value: "7" } });
    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "set-publication-v2-item-priority",
      { productionItemId: "item-ready", priority: 7 },
    ));

    fireEvent.click(screen.getByRole("tab", { name: "Каналы" }));
    fireEvent.click(screen.getByRole("button", { name: "Действия канала Первый канал" }));
    fireEvent.change(screen.getByLabelText("Timezone канала"), { target: { value: "America/New_York" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "save-publication-v2-rules",
      expect.objectContaining({
        rules: expect.objectContaining({
          "channel-a": expect.objectContaining({ timezone: "America/New_York" }),
        }),
      }),
    ));
  });

  it("disables header start when the current Videos selection has no uploadable snapshot", () => {
    const data = {
      ...base,
      publication: {
        ...base.publication,
        v2: {
          ...(base.publication as any).v2,
          items: {
            ...(base.publication as any).v2.items,
            "item-uploaded": {
              ...(base.publication as any).v2.items["item-uploaded"],
              metadata: { title: "Заблокированный ролик" },
            },
          },
          queue: (base.publication as any).v2.queue.map((row: any) => row.snapshotId === "snapshot-uploaded"
            ? {
                ...row,
                title: "Заблокированный ролик",
                youtubeVideoId: undefined,
                currentStage: "AUTH_CHECK",
                status: "AUTH_REQUIRED",
                active: false,
              }
            : row),
        },
      },
    } as unknown as NewsFlowSnapshot;

    render(<PublicationPage data={data} command={vi.fn().mockResolvedValue(undefined)} />);
    fireEvent.click(screen.getByLabelText("Выбрать Заблокированный ролик"));

    expect(screen.getByRole("button", { name: "Старт готовых" })).toBeDisabled();
  });

  it("starts only snapshots without a known YouTube video ID", async () => {
    const command = vi.fn().mockResolvedValue(undefined);
    render(<PublicationPage data={base} command={command} />);
    fireEvent.click(screen.getByRole("tab", { name: "Очередь" }));
    fireEvent.click(screen.getByRole("button", { name: "Запустить очередь" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("upload-publication-v2-snapshots", { snapshotIds: ["snapshot-ready"] }));
  });

  it("does not let a stale Videos selection silently scope Queue actions that show all selected", async () => {
    const data = {
      ...base,
      publication: {
        ...base.publication,
        v2: {
          ...(base.publication as any).v2,
          items: {
            ...(base.publication as any).v2.items,
            "item-second": {
              productionItemId: "item-second",
              metadata: { title: "Второй готовый ролик" },
              readiness: { state: "VIDEO_READY" },
              artifacts: { video: { path: "D:/second.mp4", exists: true } },
            },
          },
          queue: [
            ...(base.publication as any).v2.queue,
            {
              snapshotId: "snapshot-second",
              productionItemId: "item-second",
              title: "Второй готовый ролик",
              channelId: "channel-a",
              currentStage: "WAITING",
              status: "WAITING",
              active: false,
              completion: { completed: 0, total: 8 },
              steps: {},
            },
          ],
        },
      },
    } as unknown as NewsFlowSnapshot;
    const command = vi.fn().mockResolvedValue(undefined);
    render(<PublicationPage data={data} command={command} />);

    fireEvent.click(screen.getByLabelText("Выбрать Готовый ролик"));
    fireEvent.click(screen.getByRole("tab", { name: "Очередь" }));
    expect(screen.getByText("Выбрано:")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Запустить очередь" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Запустить очередь" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "upload-publication-v2-snapshots",
      { snapshotIds: ["snapshot-ready", "snapshot-second"] },
    ));
  });

  it("starts only explicitly selected queue snapshots", async () => {
    const command = vi.fn().mockResolvedValue(undefined);
    render(<PublicationPage data={base} command={command} />);
    fireEvent.click(screen.getByRole("tab", { name: "Очередь" }));
    fireEvent.click(screen.getByLabelText("Выбрать публикацию Готовый ролик"));
    fireEvent.click(screen.getByRole("button", { name: "Запустить выбранные (1)" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "upload-publication-v2-snapshots",
      { snapshotIds: ["snapshot-ready"] },
    ));
  });


  it("does not submit the current publication upload twice while it is pending", async () => {
    let releaseUpload: (() => void) | undefined;
    const command = vi.fn(() => new Promise<NewsFlowSnapshot | undefined>((resolve) => {
      releaseUpload = () => resolve(undefined);
    }));
    render(<PublicationPage data={base} command={command} />);
    fireEvent.click(screen.getByRole("tab", { name: "Очередь" }));
    const start = screen.getByRole("button", { name: "Запустить очередь" });
    fireEvent.click(start);
    fireEvent.click(start);

    await Promise.resolve();
    expect(command).toHaveBeenCalledTimes(1);
    expect(command).toHaveBeenCalledWith("upload-publication-v2-snapshots", { snapshotIds: ["snapshot-ready"] });
    releaseUpload?.();
    await waitFor(() => expect(screen.getByRole("button", { name: "Запустить очередь" })).toBeEnabled());
  });

  it("sends only selected production items to smart distribution preview", async () => {
    const command = vi.fn().mockResolvedValue({ ...base, publicationPreview: { assignments: [] } });
    render(<PublicationPage data={base} command={command} />);

    fireEvent.click(screen.getByLabelText("Выбрать Готовый ролик"));
    fireEvent.click(screen.getByRole("button", { name: "Распределить" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "preview-publication-v2-distribution",
      { productionItemIds: ["item-ready"] },
    ));
  });

  it("opens non-uploading distribution preview and preserves its manual lock affordance", async () => {
    const command = vi.fn().mockResolvedValue({ ...base, publicationPreview: { assignments: [{ productionItemId: "item-ready", channelId: "channel-a", source: "auto", locked: false, reason: "Квота", publishAt: "" }] } });
    render(<PublicationPage data={base} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Распределить" }));
    await waitFor(() => expect(screen.getByRole("tab", { name: "Распределение" })).toHaveAttribute("aria-selected", "true"));
    expect(screen.getByText("AUTO")).toBeInTheDocument();
    expect(command).toHaveBeenCalledWith("preview-publication-v2-distribution");
  });

  it("sends an operator-selected time range to the non-uploading distribution preview", async () => {
    const command = vi.fn().mockResolvedValue({ ...base, publicationPreview: { assignments: [] } });
    render(<PublicationPage data={base} command={command} />);

    fireEvent.click(screen.getByRole("tab", { name: "Распределение" }));
    fireEvent.change(screen.getByLabelText("Дата диапазона"), { target: { value: "2026-11-15" } });
    fireEvent.change(screen.getByLabelText("Начало диапазона"), { target: { value: "04:00" } });
    fireEvent.change(screen.getByLabelText("Конец диапазона"), { target: { value: "10:00" } });
    fireEvent.change(screen.getByLabelText("Максимум роликов на канал"), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "Показать диапазон" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith("preview-publication-v2-distribution", {
      bulkSchedule: {
        date: "2026-11-15", startTime: "04:00", endTime: "10:00", timezone: "Europe/Minsk",
        channelIds: ["channel-a"], maxPerChannel: 4,
      },
    }));
  });

  it("explains channel-capacity exhaustion in Russian instead of exposing the raw runtime code", async () => {
    const command = vi.fn().mockResolvedValue({ ...base, publicationPreview: { assignments: [{ productionItemId: "item-ready", channelId: "", source: "", locked: false, reason: "quota_exhausted", publishAt: "" }] } });
    render(<PublicationPage data={base} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "Распределить" }));

    await waitFor(() => expect(screen.getByText("Нет свободной квоты у выбранных каналов")).toBeInTheDocument());
    expect(screen.queryByText("quota_exhausted")).not.toBeInTheDocument();
  });

  it("renders per-channel quarter-hour day plan from the preview", async () => {
    const command = vi.fn().mockResolvedValue({ ...base, publicationPreview: { assignments: [
      { productionItemId: "item-ready", channelId: "channel-a", source: "auto", locked: false, reason: "balanced", publishAt: "2026-11-15T04:00:00+03:00" },
      { productionItemId: "item-uploaded", channelId: "channel-a", source: "auto", locked: false, reason: "balanced", publishAt: "2026-11-15T04:15:00+03:00" },
    ] } });
    render(<PublicationPage data={base} command={command} />);

    fireEvent.click(screen.getByRole("button", { name: "Распределить" }));

    await waitFor(() => expect(screen.getByRole("tab", { name: "Распределение" })).toHaveAttribute("aria-selected", "true"));
    fireEvent.click(screen.getByRole("tab", { name: "План дня" }));
    expect(screen.getByRole("region", { name: "План публикаций на сутки" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "04:00" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "04:15" })).toBeInTheDocument();
    expect(screen.getByText("Готовый ролик", { selector: ".nf-day-plan td span" })).toBeInTheDocument();
  });

  it("can undo a manual distribution edit before confirmation", async () => {
    const command = vi.fn().mockResolvedValue({ ...base, publicationPreview: { assignments: [{ productionItemId: "item-ready", channelId: "channel-a", source: "auto", locked: false, reason: "balanced", publishAt: "2026-11-15T04:00:00+03:00" }] } });
    render(<PublicationPage data={base} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Распределить" }));
    await waitFor(() => expect(screen.getByRole("tab", { name: "Распределение" })).toHaveAttribute("aria-selected", "true"));

    const channelSelect = screen.getByLabelText("Канал для Готовый ролик");
    fireEvent.change(channelSelect, { target: { value: "" } });
    expect(channelSelect).toHaveValue("");
    fireEvent.click(screen.getByRole("button", { name: "Отменить изменение" }));
    await waitFor(() => expect(screen.getByLabelText("Канал для Готовый ролик")).toHaveValue("channel-a"));
  });

  it("shows the preview in a 15-minute day-plan grid", async () => {
    const command = vi.fn().mockResolvedValue({ ...base, publicationPreview: { assignments: [{ productionItemId: "item-ready", channelId: "channel-a", source: "auto", locked: false, reason: "balanced", publishAt: "2026-11-15T04:15:00+03:00" }] } });
    render(<PublicationPage data={base} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Распределить" }));
    await waitFor(() => expect(screen.getByRole("tab", { name: "Распределение" })).toHaveAttribute("aria-selected", "true"));
    fireEvent.click(screen.getByRole("tab", { name: "План дня" }));

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "04:15" })).toBeInTheDocument();
    expect(screen.getByText("Готовый ролик")).toBeInTheDocument();
  });

  it("stays on Distribution when confirmation returns no state after a command failure", async () => {
    const command = vi.fn().mockImplementation((name) => {
      if (name === "preview-publication-v2-distribution") {
        return Promise.resolve({
          ...base,
          publicationPreview: {
            assignments: [{
              productionItemId: "item-ready",
              channelId: "channel-a",
              source: "auto",
              locked: false,
              reason: "balanced",
              publishAt: "2026-11-15T04:00:00+03:00",
            }],
          },
        });
      }
      if (name === "confirm-publication-v2-distribution") return Promise.resolve(undefined);
      return Promise.resolve(undefined);
    });

    render(<PublicationPage data={base} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Распределить" }));
    const confirm = await screen.findByRole("button", { name: "Подтвердить назначения" });
    fireEvent.click(confirm);

    await waitFor(() => expect(command).toHaveBeenCalledWith(
      "confirm-publication-v2-distribution",
      expect.any(Object),
    ));
    expect(screen.getByRole("tab", { name: "Распределение" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Очередь" })).toHaveAttribute("aria-selected", "false");
  });

  it("does not submit distribution confirmation twice while the first confirm is pending", async () => {
    const releases: Array<() => void> = [];
    const command = vi.fn().mockImplementation((name) => {
      if (name === "preview-publication-v2-distribution") {
        return Promise.resolve({
          ...base,
          publicationPreview: {
            assignments: [{
              productionItemId: "item-ready",
              channelId: "channel-a",
              source: "auto",
              locked: false,
              reason: "balanced",
              publishAt: "2026-11-15T04:00:00+03:00",
            }],
          },
        });
      }
      if (name === "confirm-publication-v2-distribution") {
        return new Promise<NewsFlowSnapshot | undefined>((resolve) => {
          releases.push(() => resolve(base));
        });
      }
      return Promise.resolve(undefined);
    });

    render(<PublicationPage data={base} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Распределить" }));
    const confirm = await screen.findByRole("button", { name: "Подтвердить назначения" });

    fireEvent.click(confirm);
    fireEvent.click(confirm);
    await Promise.resolve();

    const confirmCalls = command.mock.calls.filter(([name]) => name === "confirm-publication-v2-distribution");
    releases.forEach((release) => release());
    expect(confirmCalls).toHaveLength(1);
  });

  it("blocks confirmation in the UI when preview reports a scheduling conflict", async () => {
    const command = vi.fn().mockResolvedValue({ ...base, publicationPreview: { assignments: [{ productionItemId: "item-ready", channelId: "channel-a", source: "manual", locked: true, reason: "Ручное назначение", publishAt: "2026-09-11T22:00:00", scheduleWarning: "Вне окна публикации", scheduleSuggestion: "Перенесите ролик внутрь окна публикации канала." }] } });
    render(<PublicationPage data={base} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Распределить" }));
    await waitFor(() => expect(screen.getByText("Вне окна публикации")).toBeInTheDocument());
    expect(screen.getAllByText(/Перенесите ролик внутрь окна публикации канала/).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Подтвердить назначения" })).toBeDisabled();
  });
});
