import type { Meta, StoryObj } from "@storybook/nextjs";
import { EmployerContradictionList } from "./EmployerContradictionList";

const meta: Meta<typeof EmployerContradictionList> = { title: "Mothership/EmployerContradictionList", component: EmployerContradictionList, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof EmployerContradictionList>;

export const Default: Story = { args: { contradictions: [{ field: "remote", message: "Listed as remote but onsite required" }] } };
export const Empty: Story = { args: { contradictions: [] } };