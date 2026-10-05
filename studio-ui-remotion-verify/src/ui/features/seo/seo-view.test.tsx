import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { fallback, Seo, Tags } from "../../App";

describe("SEO and Tags Light views", () => {
  it("keeps SEO and tags in one Distribution workspace", () => {
    const command = vi.fn();
    const { unmount } = render(<Seo data={fallback} command={command} />);
    expect(screen.getByLabelText("Distribution workspace: SEO")).toBeTruthy();
    unmount();

    render(<Tags data={fallback} command={command} />);
    expect(screen.getByLabelText("Distribution workspace: Tags")).toBeTruthy();
  });

  it("moves metadata configuration out of the active editorial result desk", () => {
    const { unmount } = render(<Seo data={fallback} command={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Настроить SEO" })).toBeTruthy();
    expect(screen.queryByText("Промпт SEO")).toBeNull();
    unmount();

    render(<Tags data={fallback} command={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Настроить теги" })).toBeTruthy();
    expect(screen.queryByText("Промпт тегов")).toBeNull();
  });

  it("keeps the current SEO generation contract", () => {
    const seoCommand = vi.fn();
    render(<Seo data={fallback} command={seoCommand} />);
    fireEvent.click(screen.getByRole("button", { name: "Настроить SEO" }));
    fireEvent.click(screen.getByRole("button", { name: "Создать SEO и хештеги" }));
    expect(seoCommand).toHaveBeenCalledWith("generate-seo", { indices: [], provider: "agent" });

  });

  it("keeps the current tags generation contract", () => {
    const tagsCommand = vi.fn();
    render(<Tags data={{ ...fallback, seo: [{ source_title: "Ормуз" }] }} command={tagsCommand} />);
    fireEvent.click(screen.getByRole("button", { name: "Настроить теги" }));
    fireEvent.click(screen.getByRole("button", { name: "Создать теги" }));
    expect(tagsCommand).toHaveBeenCalledWith("generate-tags", { indices: [], provider: "agent" });
  });

  it("does not offer a YouTube tag limit above 500 characters", () => {
    render(<Tags data={fallback} command={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Настроить теги" }));
    expect(screen.getByLabelText(/Лимит тегов, символов/i).getAttribute("max")).toBe("500");
  });

  it("opens and saves the selected SEO package by ProductionItem ID", async () => {
    const data = {
      ...fallback,
      seo: [{
        production_item_id: "production:seo-open-edit",
        source_title: "SEO topic",
        description: "Saved SEO description",
        hashtags: ["#seo"],
        tags: ["seo tag"],
        status: "Готово",
      }],
    };
    const command = vi.fn().mockResolvedValue(data);
    render(<Seo data={data} command={command} />);

    fireEvent.click(screen.getByText("SEO topic").closest("button")!);
    fireEvent.click(screen.getByRole("button", { name: "Открыть / редактировать" }));
    expect(screen.getByText("Просмотр и редактирование SEO")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Сохранить SEO" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-seo-text", {
      productionItemId: "production:seo-open-edit",
      description: "Saved SEO description",
      hashtags: "#seo",
    }));
  });

  it("opens and saves the selected tag set by ProductionItem ID", async () => {
    const data = {
      ...fallback,
      seo: [{
        production_item_id: "production:tags-open-edit",
        source_title: "Tags topic",
        tags: ["first tag", "second tag"],
        tags_status: "Готово",
      }],
    };
    const command = vi.fn().mockResolvedValue(data);
    render(<Tags data={data} command={command} />);

    fireEvent.click(screen.getByText("Tags topic").closest("button")!);
    fireEvent.click(screen.getByRole("button", { name: "Открыть / редактировать" }));
    expect(screen.getByText("Просмотр и редактирование тегов")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Сохранить теги" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-tags-text", {
      productionItemId: "production:tags-open-edit",
      tags: "first tag, second tag",
    }));
  });
});
