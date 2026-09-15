export type WorkspaceSearchItem = {
  id: string;
  kind: "Topic" | "ProductionItem" | "Script" | "MP3" | "Cover" | "Montage" | "Publication receipt";
  title: string;
  page: "ideas" | "scripts" | "audio" | "coverGallery" | "editor" | "publication";
};

export function buildWorkspaceSearchItems(data: NewsFlowSnapshot): WorkspaceSearchItem[] {
  const topics = data.ideaTopics.map((title, index) => ({ id: `topic-${index}`, kind: "Topic" as const, title, page: "ideas" as const }));
  const productionItems = (data.ideaProductionItems || []).map((item, index) => ({ id: `production-${index}`, kind: "ProductionItem" as const, title: item.title, page: "ideas" as const }));
  const scripts = data.scenarios.map((item) => ({ id: `script-${item.index}`, kind: "Script" as const, title: item.title, page: "scripts" as const }));
  const voice = data.voiceItems.map((item) => ({ id: `voice-${item.productionItemId || item.index}`, kind: "MP3" as const, title: item.title, page: "audio" as const }));
  const covers = data.covers.map((item, index) => ({ id: `cover-${item.scenario_index ?? index}`, kind: "Cover" as const, title: item.title, page: "coverGallery" as const }));
  const montage = data.montageTasks.map((item) => ({ id: `montage-${item.scenarioIndex ?? item.index}`, kind: "Montage" as const, title: item.title, page: "editor" as const }));
  const receipts = Object.entries(data.publication.v2?.receipts || {}).map(([id, receipt]) => ({ id: `receipt-${id}`, kind: "Publication receipt" as const, title: receipt.title || receipt.productionItemId || id, page: "publication" as const }));
  return [...topics, ...productionItems, ...scripts, ...voice, ...covers, ...montage, ...receipts];
}
