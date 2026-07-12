import type { Meta, StoryObj } from "@storybook/nextjs";
import LocaleSwitcher from "./LocaleSwitcher";

const meta: Meta<typeof LocaleSwitcher> = { title: "Components/LocaleSwitcher", component: LocaleSwitcher, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof LocaleSwitcher>;

export const Default: Story = { args: { currentLocale: "en" } };
export const Chinese: Story = { args: { currentLocale: "zh" } };