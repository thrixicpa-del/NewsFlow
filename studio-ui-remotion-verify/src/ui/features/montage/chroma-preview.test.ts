import { describe, expect, it } from "vitest";
import * as preview from "./MontageOverlays";

describe("local chromakey preview pixels", () => {
  it("removes the selected green key, keeps red foreground and preserves existing alpha", () => {
    const pixels = new Uint8ClampedArray([0, 255, 0, 255, 255, 0, 0, 255, 255, 0, 0, 80]);
    const keyPixels = (preview as unknown as { keyPreviewPixels: (pixels: Uint8ClampedArray, color: string, similarity: number, blend: number) => void }).keyPreviewPixels;
    keyPixels(pixels, "#00FF00", 0.1, 0.05);
    expect(Array.from(pixels)).toEqual([0, 255, 0, 0, 255, 0, 0, 255, 255, 0, 0, 80]);
  });
  it("softens the edge around a user-selected blue key", () => {
    const pixels = new Uint8ClampedArray([0, 0, 255, 255, 0, 0, 200, 255, 255, 255, 0, 255]);
    const keyPixels = (preview as unknown as { keyPreviewPixels: (pixels: Uint8ClampedArray, color: string, similarity: number, blend: number) => void }).keyPreviewPixels;
    keyPixels(pixels, "#0000FF", 0.1, 0.1);
    expect(pixels[3]).toBe(0);
    expect(pixels[7]).toBeGreaterThan(0);
    expect(pixels[7]).toBeLessThan(255);
    expect(pixels[11]).toBe(255);
  });
});
