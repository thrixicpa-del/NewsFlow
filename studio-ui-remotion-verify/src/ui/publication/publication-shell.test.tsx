import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "../App";

describe("Publication V2 shell", () => {
  it("uses the V2 header as the only publication header and counter source", () => {
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "ПУБЛИКАЦИЯ" }));
    fireEvent.click(screen.getByRole("button", { name: "Публикация YouTube" }));

    expect(screen.getAllByRole("heading", { name: "Публикация YouTube" })).toHaveLength(1);
    expect(screen.queryByText("Ожидают")).not.toBeInTheDocument();
    expect(screen.queryByText("В работе")).not.toBeInTheDocument();
    expect(screen.queryByText("Готово")).not.toBeInTheDocument();
  });
});
