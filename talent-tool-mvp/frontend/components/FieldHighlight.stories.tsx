import type { Meta, StoryObj } from "@storybook/nextjs";
import FieldHighlight from "./FieldHighlight";

const meta: Meta<typeof FieldHighlight> = { title: "Components/FieldHighlight", component: FieldHighlight, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof FieldHighlight>;

export const Default: Story = { args: { text: "Sarah has 8 years of experience", highlight: "8 years" } };