import type { Meta, StoryObj } from "@storybook/nextjs";
import ThemeProvider from "./ThemeProvider";

const meta: Meta<typeof ThemeProvider> = { title: "Components/ThemeProvider", component: ThemeProvider, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof ThemeProvider>;

export const Light: Story = { args: { defaultTheme: "light", children: <div>content</div> } };
export const Dark: Story = { args: { defaultTheme: "dark", children: <div>content</div> } };