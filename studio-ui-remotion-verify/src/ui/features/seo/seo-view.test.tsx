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

  it("keeps the opened SEO item bound to its ProductionItem ID after queue reorder", async () => {
    const chosen = {
      production_item_id: "production:seo-chosen",
      source_title: "Chosen SEO",
      description: "Chosen description",
      hashtags: ["#chosen"],
      tags: ["chosen tag"],
      status: "Готово",
    };
    const other = {
      production_item_id: "production:seo-other",
      source_title: "Other SEO",
      description: "Other description",
      hashtags: ["#other"],
      tags: ["other tag"],
      status: "Готово",
    };
    const command = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(
      <Seo data={{ ...fallback, seo: [chosen, other] }} command={command} />,
    );

    fireEvent.click(screen.getByText("Chosen SEO").closest("button")!);
    fireEvent.click(screen.getByRole("button", { name: "Открыть / редактировать" }));
    rerender(<Seo data={{ ...fallback, seo: [other, chosen] }} command={command} />);

    expect(screen.getByDisplayValue("Chosen description")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Сохранить SEO" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-seo-text", {
      productionItemId: "production:seo-chosen",
      description: "Chosen description",
      hashtags: "#chosen",
    }));
  });

  it("still sends the durable SEO identity when the opened row disappeared", async () => {
    const chosen = {
      production_item_id: "production:seo-missing",
      source_title: "Missing SEO",
      description: "Draft description",
      hashtags: ["#draft"],
      status: "Готово",
    };
    const command = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(
      <Seo data={{ ...fallback, seo: [chosen] }} command={command} />,
    );

    fireEvent.click(screen.getByText("Missing SEO").closest("button")!);
    fireEvent.click(screen.getByRole("button", { name: "Открыть / редактировать" }));
    rerender(<Seo data={{ ...fallback, seo: [] }} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Сохранить SEO" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith("save-seo-text", {
      productionItemId: "production:seo-missing",
      description: "Draft description",
      hashtags: "#draft",
    }));
  });

  it("keeps the opened tag set bound to its ProductionItem ID after queue reorder", async () => {
    const chosen = {
      production_item_id: "production:tags-chosen",
      source_title: "Chosen Tags",
      tags: ["chosen one", "chosen two"],
      tags_status: "Готово",
    };
    const other = {
      production_item_id: "production:tags-other",
      source_title: "Other Tags",
      tags: ["other"],
      tags_status: "Готово",
    };
    const command = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(
      <Tags data={{ ...fallback, seo: [chosen, other] }} command={command} />,
    );

    fireEvent.click(screen.getByText("Chosen Tags").closest("button")!);
    fireEvent.click(screen.getByRole("button", { name: "Открыть / редактировать" }));
    rerender(<Tags data={{ ...fallback, seo: [other, chosen] }} command={command} />);

    expect(screen.getByDisplayValue("chosen one, chosen two")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Сохранить теги" }));
    await waitFor(() => expect(command).toHaveBeenCalledWith("save-tags-text", {
      productionItemId: "production:tags-chosen",
      tags: "chosen one, chosen two",
    }));
  });

  it("still sends the durable tag identity when the opened row disappeared", async () => {
    const chosen = {
      production_item_id: "production:tags-missing",
      source_title: "Missing Tags",
      tags: ["draft tag"],
      tags_status: "Готово",
    };
    const command = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(
      <Tags data={{ ...fallback, seo: [chosen] }} command={command} />,
    );

    fireEvent.click(screen.getByText("Missing Tags").closest("button")!);
    fireEvent.click(screen.getByRole("button", { name: "Открыть / редактировать" }));
    rerender(<Tags data={{ ...fallback, seo: [] }} command={command} />);
    fireEvent.click(screen.getByRole("button", { name: "Сохранить теги" }));

    await waitFor(() => expect(command).toHaveBeenCalledWith("save-tags-text", {
      productionItemId: "production:tags-missing",
      tags: "draft tag",
    }));
  });

});
