import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PublicationPage } from "./PublicationPage";
import { PublicationHistory } from "./PublicationHistory";

const command = vi.fn().mockResolvedValue(undefined);

const fixture = {
  channels: Array.from({ length: 8 }, (_, index) => ({
    id: `channel-${index + 1}`,
    channel: `channel-${index + 1}`,
    name: `Канал ${index + 1}`,
    subscribers: "10 000",
    status: "Подключён",
    oauthConnected: index !== 7,
    monetaryAccess: index < 2,
  })),
  publication: {
    uploadConcurrency: 6,
    v2: {
      items: Object.fromEntries(Array.from({ length: 84 }, (_, index) => [`item-${index + 1}`, {
        productionItemId: `item-${index + 1}`,
        metadata: { title: `Ролик ${index + 1}: длинный заголовок о международной политике и последствиях решения` },
        readiness: { state: index === 1 ? "VIDEO_MISSING" : "VIDEO_READY" },
        artifacts: { video: { path: `D:/videos/${index + 1}.mp4`, exists: index !== 1 } },
      }])),
      queue: [{
        snapshotId: "snapshot-ads", productionItemId: "item-1", title: "Ролик 1", channelId: "channel-1",
        currentStage: "ADS", status: "FORMATTING", active: false, youtubeVideoId: "yt-1",
        completion: { completed: 4, total: 12 },
        steps: { ADS: { status: "SUCCESS", providerResult: { mode: "AUTO+MANUAL", automaticSlotsEnabled: true, manualSlotsSeconds: [39, 78], confirmedManualSlotsSeconds: [39, 78] } } },
        timeline: [],
      }],
      counters: { total: 84, ready: 83 },
      paused: false,
      uploadConcurrency: 6,
      channelRules: {},
      assignments: {},
    },
  },
} as unknown as NewsFlowSnapshot;

describe("PublicationPage", () => {
  it("renders the registry-first workspace for an 84-video production batch", () => {
    render(<PublicationPage data={fixture} command={command} />);

    expect(screen.getByRole("heading", { name: "Публикация YouTube" })).toBeInTheDocument();
    expect(screen.getByText("Всего")).toBeInTheDocument();
    expect(screen.queryByText("Видео")).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Ролики" })).toHaveTextContent("84");
    expect(screen.getByRole("tab", { name: "Каналы" })).toBeInTheDocument();
    expect(screen.getByText(/Ролик 1:/)).toBeInTheDocument();
    expect(screen.getByText("MP4 отсутствует")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Очередь" }));
    expect(screen.getByRole("columnheader", { name: "Реклама" })).toBeInTheDocument();
    expect(screen.getByText("AUTO + MANUAL 39s")).toBeInTheDocument();
  });

  it("requires explicit reconciliation for an upload with unknown outcome", () => {
    const uncertainFixture = {
      ...fixture,
      publication: {
        ...fixture.publication,
        v2: {
          ...fixture.publication.v2,
          queue: [{
            snapshotId: "snapshot-uncertain", productionItemId: "item-1", title: "Ролик 1",
            channelId: "channel-1", currentStage: "VIDEO_UPLOAD", status: "USER_ACTION_REQUIRED",
            active: false, youtubeVideoId: null, completion: { completed: 1, total: 12 },
            steps: { VIDEO_UPLOAD: { status: "USER_ACTION_REQUIRED" } }, timeline: [],
          }],
        },
      },
    } as unknown as NewsFlowSnapshot;

    command.mockClear();
    render(<PublicationPage data={uncertainFixture} command={command} />);
    fireEvent.click(screen.getByRole("tab", { name: "Очередь" }));
    fireEvent.click(screen.getByRole("button", { name: "Раскрыть ход публикации Ролик 1" }));

    expect(screen.queryByRole("button", { name: /Повторить/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Отменить автоматизацию" })).not.toBeInTheDocument();
    expect(screen.getByText(/обычный retry и отмена заблокированы/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("YouTube video ID для Ролик 1"), { target: { value: "yt-verified-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Привязать найденный YouTube ID" }));
    expect(command).toHaveBeenCalledWith("resolve-publication-v2-uncertain-upload", {
      snapshotId: "snapshot-uncertain",
      outcome: "found",
      youtubeVideoId: "yt-verified-1",
    });

    fireEvent.click(screen.getByRole("button", { name: "Я проверил канал: видео нет — разрешить повтор" }));
    expect(command).toHaveBeenCalledWith("resolve-publication-v2-uncertain-upload", {
      snapshotId: "snapshot-uncertain",
      outcome: "not_found",
    });
  });

  it("keeps video-ready, new-package, and quota-slot counters semantically distinct", () => {
    const semanticFixture = {
      ...fixture,
      publication: {
        ...fixture.publication,
        readyOutputs: [],
        v2: {
          ...fixture.publication.v2,
          counters: {
            total: 84,
            videoReady: 84,
            publicationReady: 84,
            assigned: 0,
            unassigned: 84,
            quotaSlotsRemaining: 88,
          },
          items: Object.fromEntries(Array.from({ length: 84 }, (_, index) => [`item-${index + 1}`, {
            productionItemId: `item-${index + 1}`,
            metadata: { title: `Ролик ${index + 1}` },
            readiness: { state: "VIDEO_READY", videoReady: true, publicationReady: true },
            artifacts: { video: { path: `D:/videos/${index + 1}.mp4`, exists: true } },
          }])),
        },
      },
    } as unknown as NewsFlowSnapshot;

    render(<PublicationPage data={semanticFixture} command={command} />);

    const metricValue = (label: string) => screen.getByText(label).closest(".nf-kpi")?.querySelector("b");
    expect(metricValue("MP4 готовы")).toHaveTextContent("84");
    expect(metricValue("Новые packages")).toHaveTextContent("0");
    expect(metricValue("Свободно по квотам")).toHaveTextContent("88");
  });

  it("keeps ProductionItem ID inspectable without replacing the human video title", () => {
    render(<PublicationPage data={fixture} command={command} />);

    expect(screen.getByText(/Ролик 1:/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Раскрыть детали Ролик 1:/ }));

    expect(screen.getByText("ProductionItem ID")).toBeInTheDocument();
    expect(screen.getByText("item-1")).toBeInTheDocument();
  });

  it("shows snapshot-backed provenance for a publication receipt", () => {
    render(<PublicationHistory rows={[{
      snapshotId: "receipt-42",
      productionItemId: "item-ormuz",
      title: "Ормуз",
      channelId: "channel-1",
      channelName: "Канал 1",
      youtubeVideoId: "video-42",
      youtubeVideoUrl: "https://youtube.example/video-42",
      requestedPublishAt: "2026-09-15T12:00:00Z",
      confirmedPublishAt: "2026-09-15T12:10:00Z",
      finalStatus: "DONE",
      completion: "3/3",
      duration: "42.0",
      ads: { status: "SUCCESS", mode: "AUTO+MANUAL", automatic: true, manualSlotsSeconds: [39, 78], confirmedManualSlotsSeconds: [39, 78] },
      stages: { ADS: "SUCCESS", DONE: "SUCCESS" },
    }]} />);

    fireEvent.click(screen.getByRole("button", { name: "Ормуз" }));

    expect(screen.getByText("Snapshot ID")).toBeInTheDocument();
    expect(screen.getByText("receipt-42")).toBeInTheDocument();
    expect(screen.getAllByText("Реклама").length).toBeGreaterThan(0);
    expect(screen.getAllByText("AUTO + MANUAL 39s").length).toBeGreaterThan(0);
    expect(screen.getByText("Ручные рекламные слоты")).toBeInTheDocument();
    expect(screen.getByText("Текущий snapshot не сообщает признак устаревания")).toBeInTheDocument();
  });
});
