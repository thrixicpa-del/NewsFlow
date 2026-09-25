import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import { ContextInspector } from "../layout/ContextInspector";
import { Sidebar } from "../layout/Sidebar";
import { TaskCenter } from "../features/task-center/TaskCenter";
import type { TaskCenterEntry } from "../features/task-center/task-model";

const meta = {
  title: "Composites/Workstation controls",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const queueSnapshot = {
  scenarios: [],
  covers: [{ title: "Ормуз: cover generation", status: "Генерация", progress: 42 }],
  voiceItems: [{ index: 1, title: "Ормуз: voice", state: "В обработке", path: "", voiceProgress: 65 }],
  montageTasks: [{ index: 1, title: "Ормуз: Fast News montage", status: "Планирование", progress: 18 }],
  publication: { v2: { queue: [{ snapshotId: "pub-1", productionItemId: "prod-084", title: "Ормуз: публикация", channelId: "channel-1", publishMode: "scheduled", status: "WAITING", currentStage: "Проверка readiness", active: true, completion: { completed: 2, total: 5 }, steps: {} }] } },
} as unknown as NewsFlowSnapshot;

export const TaskCenterAndInspector: Story = {
  render: () => {
    const [entry, setEntry] = useState<TaskCenterEntry | null>(null);
    const [width, setWidth] = useState(360);
    const [density, setDensity] = useState<"comfortable" | "compact">("comfortable");
    const [inspectorVisible, setInspectorVisible] = useState(true);
    return <main className="nf-app-shell" style={{ gridTemplateColumns: "minmax(0, 1fr) 380px", minHeight: "100vh", padding: 24 }}>
      <TaskCenter data={queueSnapshot} onSelect={(nextEntry) => {
        setEntry(nextEntry);
        setInspectorVisible(true);
      }} />
      {inspectorVisible ? (
        <ContextInspector
          entry={entry}
          width={width}
          density={density}
          onDensityChange={setDensity}
          onWidthChange={setWidth}
          onClose={() => setEntry(null)}
          onHide={() => setInspectorVisible(false)}
        />
      ) : (
        <button type="button" onClick={() => setInspectorVisible(true)}>Развернуть инспектор</button>
      )}
    </main>;
  },
};

export const NavigationRail: Story = {
  render: () => {
    const [collapsed, setCollapsed] = useState(false);
    return <div style={{ width: collapsed ? 88 : 280, minHeight: "100vh" }}><Sidebar brand={<strong>NEWSFLOW</strong>} status="Система готова" collapsed={collapsed} onToggle={() => setCollapsed((value) => !value)}><button className="active">Центр управления</button><button>Генерация идей</button><button>Сценарии</button><button>Обложки YouTube</button><button>Монтаж</button><button>Публикация</button></Sidebar></div>;
  },
};
