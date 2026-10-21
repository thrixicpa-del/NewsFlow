import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ frame: 71 }));
vi.mock("remotion", () => ({
  AbsoluteFill: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Sequence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useCurrentFrame: () => state.frame,
  useVideoConfig: () => ({ fps: 30 }),
  Easing: { bezier: () => undefined },
  interpolate: () => 1,
}));
vi.mock("@remotion/media", () => ({
  Audio: () => null,
  Video: ({ style, volume, trimBefore }: { style: React.CSSProperties; volume: number; trimBefore: number }) =>
    <div data-testid="video" style={style} data-volume={volume} data-trim={trimBefore} />,
}));
import { localVideoZoomScale, NewsFlowMontage } from "../../../../remotion/src/timeline";

describe("Remotion local zoom", () => {
  it("clamps to 100–108% for the same 72 frames", () => {
    expect(localVideoZoomScale(-1, 72)).toBe(1);
    expect(localVideoZoomScale(0, 72)).toBe(1);
    expect(localVideoZoomScale(71, 72)).toBe(1.08);
    expect(localVideoZoomScale(90, 72)).toBe(1.08);
  });
  it("applies one scale and retains the selected source offset and silence", () => {
    render(<NewsFlowMontage project={{ fps: 30, aspectRatio: "16:9", durationInFrames: 72,
      sequences: [{ kind: "footage", src: "test.mp4", from: 0, durationInFrames: 72, sourceStart: 3, localVideoZoom: true }],
      voiceover: { src: "", from: 0 }, transitionStyle: "cut" }} />);
    const video = screen.getByTestId("video");
    expect(video.style.scale).toBe("1");
    expect(video.style.transform).toContain("scale(1.08)");
    expect(video.getAttribute("data-trim")).toBe("90");
    expect(video.getAttribute("data-volume")).toBe("0");
  });
});
