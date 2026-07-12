import type { Meta, StoryObj } from "@storybook/nextjs";
import { StakeholderMatrix } from "./StakeholderMatrix";

const meta: Meta<typeof StakeholderMatrix> = { title: "Mothership/StakeholderMatrix", component: StakeholderMatrix, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof StakeholderMatrix>;

export const Default: Story = { args: { stakeholders: [{ name: "CEO", role: "Decision maker" }, { name: "Hiring Manager", role: "Evaluator" }] } };
export const Empty: Story = { args: { stakeholders: [] } };