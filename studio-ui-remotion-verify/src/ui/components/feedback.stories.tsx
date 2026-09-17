import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import { AlertDialog } from "./alert-dialog";
import { Badge } from "./badge";
import { Button } from "./button";
import { Dialog } from "./dialog";
import { DropdownMenu } from "./dropdown-menu";
import { EmptyState, ErrorState, LoadingState } from "./states";
import { Popover } from "./popover";
import { Progress } from "./progress";
import { Sheet } from "./sheet";
import { StatusBadge, type UiJobStatus } from "./status-badge";
import { Toast } from "./toast";
import { Tooltip } from "./tooltip";

const meta = {
  title: "Primitives/Feedback and overlays",
  parameters: { layout: "padded" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const Statuses: Story = {
  render: () => <div style={{ display: "grid", gap: 18, maxWidth: 720 }}>
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}><Badge>Черновик</Badge><Badge tone="info">Проверка</Badge><Badge tone="success">Готово</Badge><Badge tone="warning">Ожидает</Badge><Badge tone="danger">Ошибка</Badge></div>
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>{(["QUEUED", "RUNNING", "WAITING", "READY", "FAILED", "CANCELLED"] as UiJobStatus[]).map((status) => <StatusBadge key={status} status={status} />)}</div>
    <Progress value={64} label="Подготовка монтажа: 64%" />
    <LoadingState label="Проверяем текущую очередь" />
    <EmptyState title="Нет новых предложений" description="Новые результаты появятся здесь после реального запроса к текущему provider path." action={<Button>Открыть редактор</Button>} />
    <ErrorState title="Provider временно недоступен" description="Исходные данные не потеряны. Повторите только текущую задачу после проверки доступа." action={<Button variant="secondary">Повторить</Button>} />
    <Toast tone="success" message="Настройки сохранены в тестовом профиле." />
  </div>,
};

export const Overlays: Story = {
  render: () => {
    const [dialogOpen, setDialogOpen] = useState(false);
    const [sheetOpen, setSheetOpen] = useState(false);
    const [alertOpen, setAlertOpen] = useState(false);
    return <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
      <Button onClick={() => setDialogOpen(true)}>Открыть диалог</Button>
      <Button onClick={() => setSheetOpen(true)}>Открыть Sheet</Button>
      <Button variant="destructive" onClick={() => setAlertOpen(true)}>Открыть подтверждение</Button>
      <DropdownMenu label="Дополнительные действия"><button type="button">Скопировать ID</button><button type="button">Экспортировать статус</button></DropdownMenu>
      <Popover label="Детали"><p style={{ margin: 0 }}>Полезный контекст без изменения очереди.</p></Popover>
      <Tooltip content="Подсказка доступна при наведении"><Button variant="ghost">Навести курсор</Button></Tooltip>
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen} title="Новая тема" description="Пример диалога shared UI kit"><p>Существующие handlers не выполняются из Storybook.</p></Dialog>
      <Sheet open={sheetOpen} onOpenChange={setSheetOpen} title="Контекст задачи" description="Панель показывает текущий snapshot"><p>Здесь появляется только runtime-данные, уже доступные приложению.</p></Sheet>
      <AlertDialog open={alertOpen} onOpenChange={setAlertOpen} title="Удалить выбранные темы?" description="Подтвердите точечное изменение test state." confirmLabel="Удалить" onConfirm={() => setAlertOpen(false)} />
    </div>;
  },
};
