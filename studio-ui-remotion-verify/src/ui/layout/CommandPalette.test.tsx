import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CommandPalette } from "./CommandPalette";

describe("CommandPalette", () => {
  it("filters current snapshot search items and navigates without firing a job", () => {
    const onNavigate = vi.fn();
    const onOpenChange = vi.fn();
    render(<CommandPalette open onOpenChange={onOpenChange} onNavigate={onNavigate} items={[
      { id: "voice-p1", kind: "MP3", title: "Ормуз — озвучка", page: "audio" },
      { id: "cover-p1", kind: "Cover", title: "Ормуз — обложка", page: "coverGallery" },
    ]} />);

    fireEvent.change(screen.getByRole("textbox", { name: "Поиск по NewsFlow" }), { target: { value: "озвучка" } });
    fireEvent.click(screen.getByRole("option", { name: /Ормуз — озвучка/ }));
    expect(onNavigate).toHaveBeenCalledWith("audio");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
