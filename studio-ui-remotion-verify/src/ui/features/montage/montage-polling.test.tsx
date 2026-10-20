import { act, cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Editor, fallback } from "../../App";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const pending = {
  ...fallback,
  montageSettings: {
    ...fallback.montageSettings,
    renderer: "ffmpeg" as const,
    queueRunning: false,
  },
  montageTasks: [
    {
      index: 0,
      title: "Technical block fixture",
      status: "Планирование сцен",
      runtimeCurrent: true,
    },
  ],
};

describe("Montage result polling", () => {
  it("keeps reading a current-session active task after the owner probe turns false, then stops on its terminal snapshot", async () => {
    vi.useFakeTimers();
    const refresh = vi.fn(async () => undefined);
    const command = vi.fn();
    const view = render(
      <Editor data={pending} command={command} refresh={refresh} />,
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1900);
    });
    expect(refresh.mock.calls.length).toBeGreaterThanOrEqual(2);
    view.rerender(
      <Editor
        data={{
          ...pending,
          montageTasks: [{ ...pending.montageTasks[0], status: "Готово" }],
        }}
        command={command}
        refresh={refresh}
      />,
    );
    const before = refresh.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(refresh).toHaveBeenCalledTimes(before);
    expect(command).not.toHaveBeenCalled();
  });

  it("does not poll an abandoned task from a previous process when no queue owner is alive", async () => {
    vi.useFakeTimers();
    const refresh = vi.fn(async () => undefined);
    render(
      <Editor
        data={{
          ...pending,
          montageTasks: [{ ...pending.montageTasks[0], runtimeCurrent: false }],
        }}
        command={vi.fn()}
        refresh={refresh}
      />,
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(refresh).not.toHaveBeenCalled();
  });
});
