import type { Meta, StoryObj } from "@storybook/react-vite";
import { Plus, SlidersHorizontal } from "lucide-react";
import { useState } from "react";
import { Button } from "./button";
import { Checkbox } from "./checkbox";
import { IconButton } from "./icon-button";
import { Input } from "./input";
import { Select } from "./select";
import { Switch } from "./switch";
import { Tabs, type TabItem } from "./tabs";
import { Textarea } from "./textarea";
import { Toolbar } from "./toolbar";

const meta = {
  title: "Primitives/Forms and actions",
  parameters: { layout: "padded" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const Controls: Story = {
  render: () => {
    const [tab, setTab] = useState<"current" | "archive">("current");
    const [selected, setSelected] = useState(false);
    const [enabled, setEnabled] = useState(true);
    return <div style={{ display: "grid", gap: 20, maxWidth: 680 }}>
      <Toolbar label="Действия темы"><Button variant="primary"><Plus size={16} />Добавить тему</Button><Button variant="secondary">Сохранить черновик</Button><Button variant="destructive">Удалить выбранные</Button><IconButton label="Настройки отображения"><SlidersHorizontal size={16} /></IconButton></Toolbar>
      <Tabs<"current" | "archive"> items={([{"id":"current","label":"Активные","count":84},{"id":"archive","label":"Архив","count":97}] satisfies TabItem<"current" | "archive">[])} value={tab} onChange={setTab} />
      <Input label="Тема" defaultValue="Ормуз на грани: рынок ждёт шок" description="Обычный контроль текущего workstation UI." />
      <Input label="Проверка" defaultValue="" error="Укажите тему перед сохранением." />
      <Textarea label="Контекст редактора" defaultValue="Проверить влияние на нефтяной рынок и маршруты танкеров." />
      <Select label="Приоритет" defaultValue="high" options={[{ value: "high", label: "Высокий" }, { value: "normal", label: "Обычный" }, { value: "low", label: "Низкий" }]} />
      <Checkbox label="Добавить в избранное" checked={selected} onCheckedChange={setSelected} />
      <Switch label="Автоматически сохранять черновик" checked={enabled} onCheckedChange={setEnabled} />
    </div>;
  },
};

export const InteractionStates: Story = {
  render: () => <div style={{ display: "grid", gap: 16, maxWidth: 680 }}>
    <Toolbar label="Состояния действий"><Button variant="primary">Обычная primary</Button><Button variant="secondary" disabled>Недоступное действие</Button><Button variant="destructive" aria-pressed>Выбранное действие</Button></Toolbar>
    <Input label="Focus state" autoFocus defaultValue="Фокус отображается через current focus-visible tokens" />
    <Textarea label="Длинный русский заголовок" defaultValue="Крайне длинная редакционная формулировка проверяет переносы, плотность и читаемость рабочего интерфейса без изменения бизнес-логики." />
  </div>,
};
