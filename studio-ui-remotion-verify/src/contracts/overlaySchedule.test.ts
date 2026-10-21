import { describe, expect, it } from "vitest";
import type { MontageOverlayLayer } from "./montageOverlays";
import { overlayIntervals, overlaySourceTime, validOverlayTiming } from "./overlaySchedule";

const base: MontageOverlayLayer = { id: "test", name: "Test", enabled: true, path: "D:/test.png", kind: "image", x: 0, y: 0, width: 100, height: 100, keepAspect: true, opacity: 1, start: 6, duration: 2, mode: "once", repeatEvery: 10, endOffset: 5, chromaEnabled: false, chromaColor: "#00FF00", chromaSimilarity: .12, chromaBlend: .08, audioEnabled: false };
describe("final-clock overlay schedule shared with the Python contract", () => {
  it("sorts/clips manual ranges, uses half-open ends and restarts each animation", () => {
    const layer = { ...base, mode: "intervals" as const, ranges: [{ start: 80, end: 88 }, { start: 6, end: 12 }, { start: 180, end: 200 }] };
    expect(overlayIntervals(layer, 190)).toEqual([[6, 12], [80, 88], [180, 190]]);
    expect(overlaySourceTime(layer, 12, 190)).toBeNull();
    expect(overlaySourceTime(layer, 80, 190)).toBe(0);
    expect(overlayIntervals(layer, 5)).toEqual([]);
  });
  it("spreads exactly N whole shows over a window or dynamic MP4 duration", () => {
    const layer = { ...base, mode: "count" as const, repeatCount: 4, rangeEnd: 32 };
    expect(overlayIntervals(layer, 300)).toEqual([[6, 8], [14, 16], [22, 24], [30, 32]]);
    expect(overlayIntervals({ ...layer, rangeEnd: null }, 62)).toEqual([[6, 8], [24, 26], [42, 44], [60, 62]]);
    expect(overlaySourceTime(layer, 14.5, 300)).toBe(.5);
    expect(overlayIntervals({ ...layer, repeatCount: 1 }, 300)).toEqual([[6, 8]]);
  });
  it("does not hide impossible counts behind overlapping shows", () => {
    expect(() => overlayIntervals({ ...base, mode: "count", duration: 5, repeatCount: 4 }, 20)).toThrow(/не помещаются/);
    expect(validOverlayTiming({ ...base, mode: "count", duration: 5, repeatCount: 4, rangeEnd: 20 })).toBe(false);
  });
  it("uses the actual end and retains the old end/repeat semantics", () => {
    expect(overlayIntervals({ ...base, mode: "until-end" }, 300)).toEqual([[6, 300]]);
    expect(overlayIntervals({ ...base, mode: "repeat", start: 2, duration: 3, repeatEvery: 4 }, 11)).toEqual([[2, 5], [6, 9], [10, 11]]);
    expect(overlaySourceTime({ ...base, mode: "end", duration: 3, endOffset: 12 }, 0, 11)).toBe(0);
  });
  it("rejects invalid counts, overlapping ranges, unsafe windows and excessive repeats", () => {
    expect(validOverlayTiming({ ...base, mode: "count", repeatCount: 2.5 })).toBe(false);
    expect(validOverlayTiming({ ...base, mode: "count", rangeEnd: 5 })).toBe(false);
    expect(validOverlayTiming({ ...base, mode: "intervals", ranges: [{ start: 1, end: 5 }, { start: 3, end: 9 }] })).toBe(false);
    expect(() => overlayIntervals({ ...base, mode: "repeat", repeatEvery: .001 }, 1000)).toThrow();
  });
});
