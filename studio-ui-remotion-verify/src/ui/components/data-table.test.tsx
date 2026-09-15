import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ColumnDef } from "@tanstack/react-table";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DataTable } from "./data-table";

describe("DataTable keyboard workflow", () => {
  beforeEach(() => localStorage.clear());
  it("moves selection with arrows and activates a row only with Enter", () => {
    const onRowActivate = vi.fn();
    const data = [{ title: "Первая" }, { title: "Вторая" }];
    const columns: ColumnDef<(typeof data)[number]>[] = [{ accessorKey: "title", header: "Заголовок" }];
    render(<DataTable ariaLabel="Рабочая таблица" data={data} columns={columns} onRowActivate={onRowActivate} />);

    const rows = screen.getAllByRole("row");
    fireEvent.keyDown(rows[1], { key: "ArrowDown" });
    expect(document.activeElement).toBe(rows[2]);
    fireEvent.keyDown(rows[2], { key: "Enter" });
    expect(onRowActivate).toHaveBeenCalledWith(data[1]);
    fireEvent.keyDown(rows[2], { key: "Delete" });
    expect(onRowActivate).toHaveBeenCalledTimes(1);
  });

  it("keeps safe local filter, sort and column preferences outside production state", async () => {
    const data = [{ title: "Ормуз", status: "READY" }, { title: "Балтика", status: "WAITING" }];
    const columns: ColumnDef<(typeof data)[number]>[] = [
      { accessorKey: "title", header: "Тема" },
      { accessorKey: "status", header: "Статус" },
    ];
    render(<DataTable ariaLabel="Очередь обложек" data={data} columns={columns} preferenceKey="covers" />);

    fireEvent.change(screen.getByLabelText("Фильтр: Очередь обложек"), { target: { value: "Ормуз" } });
    expect(screen.getByText("Ормуз")).toBeTruthy();
    expect(screen.queryByText("Балтика")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Тема" }));
    await waitFor(() => expect(JSON.parse(localStorage.getItem("newsflow.ui-table-preferences.v1") || "{}")).toMatchObject({
      covers: { filter: "Ормуз", sort: [{ id: "title", desc: false }] },
    }));
    expect(localStorage.getItem("newsflow-settings")).toBeNull();
  });
});
