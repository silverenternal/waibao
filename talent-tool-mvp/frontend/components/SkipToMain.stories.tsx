import type { Meta, StoryObj } from "@storybook/nextjs";
import SkipToMain from "./SkipToMain";

const meta: Meta<typeof SkipToMain> = { title: "Components/SkipToMain", component: SkipToMain, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof SkipToMain>;

export const Default: Story = { args: {} };