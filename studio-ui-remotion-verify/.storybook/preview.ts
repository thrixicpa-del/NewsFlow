import type { Preview } from "@storybook/react-vite";
import "../src/ui/styles.css";

const preview: Preview = {
  parameters: {
    layout: "padded",
    backgrounds: {
      default: "newsflow-dark",
      values: [{ name: "newsflow-dark", value: "#07101d" }],
    },
  },
};

export default preview;
