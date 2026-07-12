import type { Meta, StoryObj } from "@storybook/nextjs";
import Toaster from "./sonner";

const meta: Meta<typeof Toaster> = { title: "UI/Sonner", component: Toaster, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof Toaster>;

export const Basic: Story = { render: () => <Toaster /> };