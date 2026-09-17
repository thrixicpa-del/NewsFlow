import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ColumnDef } from "@tanstack/react-table";
import { Activity, CheckCircle2, Clock3 } from "lucide-react";
import { Button } from "./button";
import { DataTable } from "./data-table";
import { PageHeader } from "./page-header";
import { StatCard } from "./stat-card";
import { Toolbar } from "./toolbar";

const meta = {
  title: "Composites/Production workspace",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

type ProductionRow = { id: string; topic: string; status: string; updated: string };
const rows: ProductionRow[] = [
  { id: "prod-084", topic: "Ормуз на грани: Иран давит на танкеры", status: "В работе", updated: "Только что" },
  { id: "prod-083", topic: "Нефтяной рынок ждёт шок", status: "Готово", updated: "12 мин назад" },
];
const columns: ColumnDef<ProductionRow>[] = [
  { accessorKey: "topic", header: "Тема" },
  { accessorKey: "status", header: "Статус" },
  { accessorKey: "updated", header: "Обновлено" },
];

export const EditorialDesk: Story = {
  render: () => <main style={{ minHeight: "100vh", padding: 32 }}>
    <PageHeader eyebrow="PRODUCTION CONTROL ROOM" title="Редакционный стол" description="Сводка намеренно показывает только реальные статусы из текущего snapshot." actions={<Toolbar><Button variant="primary">Добавить тему</Button><Button>Открыть очередь</Button></Toolbar>} meta={<><StatCard label="Активные" value="84" icon={<Activity size={16} />} /><StatCard label="Готово" value="31" tone="success" icon={<CheckCircle2 size={16} />} /><StatCard label="Ожидают" value="7" tone="warning" icon={<Clock3 size={16} />} /></>} />
    <section className="panel" style={{ padding: 20 }}><DataTable data={rows} columns={columns} ariaLabel="Активное производство" preferenceKey="storybook-production-rows" /></section>
  </main>,
};
