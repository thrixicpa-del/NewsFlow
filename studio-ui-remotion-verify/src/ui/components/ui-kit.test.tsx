import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AlertDialog } from "./alert-dialog";
import { Button } from "./button";
import { Checkbox } from "./checkbox";
import { EmptyState, ErrorState, LoadingState } from "./states";
import { IconButton } from "./icon-button";
import { Input } from "./input";
import { PageHeader } from "./page-header";
import { Select } from "./select";
import { StatCard } from "./stat-card";
import { Switch } from "./switch";
import { Textarea } from "./textarea";
import { Toolbar } from "./toolbar";

describe("shared Light UI kit", () => {
  it("exposes labelled form controls and accessible icon actions", () => {
    const onChange = vi.fn();
    render(<>
      <Input label="Название" value="" onChange={onChange} />
      <Textarea label="Описание" value="" onChange={onChange} />
      <Select label="Режим" value="fast" onChange={onChange} options={[{ value: "fast", label: "Быстрый" }]} />
      <Checkbox label="Включить" checked={false} onCheckedChange={onChange} />
      <Switch label="Автозапуск" checked={false} onCheckedChange={onChange} />
      <IconButton label="Обновить" onClick={() => undefined}>↻</IconButton>
    </>);

    expect(screen.getByLabelText("Название")).not.toBeNull();
    expect(screen.getByLabelText("Описание")).not.toBeNull();
    expect(screen.getByLabelText("Режим")).not.toBeNull();
    expect(screen.getByLabelText("Включить")).not.toBeNull();
    expect(screen.getByLabelText("Автозапуск")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Обновить" })).not.toBeNull();
  });

  it("renders common layout, state and destructive confirmation primitives", () => {
    render(<>
      <PageHeader eyebrow="NEWSFLOW" title="Центр управления" description="Статус конвейера" actions={<Button>Создать</Button>} />
      <Toolbar label="Действия"><Button>Обновить</Button></Toolbar>
      <StatCard label="Готово" value="12" tone="success" />
      <EmptyState title="Пусто" description="Добавьте первую тему" />
      <ErrorState title="Ошибка" description="Повторите действие" />
      <LoadingState label="Загрузка данных" />
    </>);

    expect(screen.getByRole("heading", { name: "Центр управления" })).not.toBeNull();
    expect(screen.getByText("Готово")).not.toBeNull();
    expect(screen.getByText("Пусто")).not.toBeNull();
    expect(screen.getByText("Ошибка")).not.toBeNull();
    expect(screen.getByRole("status", { name: "Загрузка данных" })).not.toBeNull();
  });

  it("uses an alertdialog for a destructive confirmation", () => {
    render(<AlertDialog open title="Удалить тему" description="Это действие нельзя отменить" confirmLabel="Удалить" onOpenChange={() => undefined} onConfirm={() => undefined} />);
    expect(screen.getByRole("alertdialog", { name: "Удалить тему" })).not.toBeNull();
  });
});
