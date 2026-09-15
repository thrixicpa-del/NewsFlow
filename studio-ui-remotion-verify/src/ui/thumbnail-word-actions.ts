export type CoverWordGenerationInput = {
  indices: number[];
  productionItemIds?: string[];
  provider: string;
  template?: string;
  useDefault?: boolean;
  useStructure: boolean;
  avoidRepeats: boolean;
  force?: boolean;
};

export function coverWordGenerationPayload(input: CoverWordGenerationInput) {
  return {
    indices: input.indices,
    ...(input.productionItemIds === undefined
      ? {}
      : { productionItemIds: input.productionItemIds }),
    provider: input.provider,
    ...(input.template === undefined ? {} : { template: input.template }),
    ...(input.useDefault ? { useDefault: true } : {}),
    useStructure: input.useStructure,
    avoidRepeats: input.avoidRepeats,
    ...(input.force ? { force: true, regenerate: true } : {}),
  };
}

export function coverWordPairGenerationPayload(
  input: Omit<CoverWordGenerationInput, "template" | "useDefault">,
) {
  return {
    indices: input.indices,
    provider: input.provider,
    useDefault: true,
    useStructure: input.useStructure,
    avoidRepeats: input.avoidRepeats,
    ...(input.force ? { force: true, regenerate: true } : {}),
  };
}

export function coverHeadlineProviderPayload(provider: "agent" | "openai") {
  return { headlineProvider: provider };
}

export function fastGenOperationPayload(operation: string) {
  return { operation };
}

export function coverPromptProviderPayload(provider: "agent" | "openai") {
  return { provider };
}

export function coverBuildModePayload(buildMode: string) {
  return { buildMode };
}

export function coverTextModePayload(textMode: "overlay" | "fastgen") {
  return { textMode };
}
