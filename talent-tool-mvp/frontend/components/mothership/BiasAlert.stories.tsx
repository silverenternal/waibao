import type { Meta, StoryObj } from "@storybook/nextjs";
import { BiasAlert } from "./BiasAlert";

const meta: Meta<typeof BiasAlert> = { title: "Mothership/BiasAlert", component: BiasAlert, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof BiasAlert>;

export const Default: Story = { args: { type: "gender", message: "Role wording may bias toward male candidates" } };
export const Age: Story = { args: { type: "age", message: "Phrasing may discourage older applicants" } };