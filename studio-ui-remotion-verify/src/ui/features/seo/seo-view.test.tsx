import { fireEvent, render, screen } from "@testing-library/react";
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

  it("caps the editable tag budget at YouTube's 500-character limit", () => {
    render(<Tags data={{ ...fallback, seo: [{ source_title: "Ормуз" }] }} command={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Настроить теги" }));
    expect(screen.getByLabelText("Лимит тегов, символов")).toHaveAttribute("max", "500");
  });

});
