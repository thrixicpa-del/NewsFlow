import { describe, expect, it } from "vitest";

import {
  coverHeadlineProviderPayload,
  coverPromptProviderPayload,
  coverBuildModePayload,
  coverTextModePayload,
  fastGenOperationPayload,
  coverWordPairGenerationPayload,
  coverWordGenerationPayload,
} from "./thumbnail-word-actions";

describe("coverWordGenerationPayload", () => {
  it("marks an explicit regenerate action as forced without changing the selected topics", () => {
    expect(
      coverWordGenerationPayload({
        indices: [3, 9],
        provider: "agent",
        template: "Только факты",
        useStructure: true,
        avoidRepeats: true,
        force: true,
      }),
    ).toMatchObject({
      indices: [3, 9],
      provider: "agent",
      template: "Только факты",
      useStructure: true,
      avoidRepeats: true,
      force: true,
      regenerate: true,
    });
  });

  it("persists ChatGPT selection before the next snapshot can restore the old agent value", () => {
    expect(coverHeadlineProviderPayload("openai")).toEqual({
      headlineProvider: "openai",
    });
  });

  it("persists a model selected from the FastGen model catalogue", () => {
    expect(fastGenOperationPayload("nano_banana_pro_image_generate")).toEqual({
      operation: "nano_banana_pro_image_generate",
    });
  });

  it("persists the visual prompt provider and text-face renderer mode on click", () => {
    expect(coverPromptProviderPayload("openai")).toEqual({ provider: "openai" });
    expect(coverBuildModePayload("fastgen-full")).toEqual({
      buildMode: "fastgen-full",
    });
    expect(coverTextModePayload("fastgen")).toEqual({ textMode: "fastgen" });
  });

  it("creates both thumbnail text lines through one core-template action", () => {
    expect(
      coverWordPairGenerationPayload({
        indices: [2, 7],
        provider: "openai",
        useStructure: true,
        avoidRepeats: true,
      }),
    ).toEqual({
      indices: [2, 7],
      provider: "openai",
      useDefault: true,
      useStructure: true,
      avoidRepeats: true,
    });
  });

  it("binds an explicitly selected cover job to durable ProductionItem IDs", () => {
    expect(
      coverWordGenerationPayload({
        indices: [2],
        productionItemIds: ["production:ormuz"],
        provider: "agent",
        useStructure: true,
        avoidRepeats: true,
      }),
    ).toMatchObject({
      indices: [2],
      productionItemIds: ["production:ormuz"],
    });
  });
});
