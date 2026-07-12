import type { Meta, StoryObj } from "@storybook/nextjs";
import ProductTour from "./ProductTour";

const meta: Meta<typeof ProductTour> = { title: "Components/ProductTour", component: ProductTour, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof ProductTour>;

export const Default: Story = { args: { open: true, step: 1, totalSteps: 4 } };
export const Complete: Story = { args: { open: true, step: 4, totalSteps: 4 } };