import type { Meta, StoryObj } from "@storybook/nextjs";
import ATSConflictResolver from "./ATSConflictResolver";

const meta: Meta<typeof ATSConflictResolver> = { title: "Components/ATSConflictResolver", component: ATSConflictResolver, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof ATSConflictResolver>;

export const Default: Story = { args: { conflicts: [{ field: "email", values: [{ source: "bullhorn", value: "s@l.com" }, { source: "linkedin", value: "s.lee@gmail.com" }] }] } };
export const Empty: Story = { args: { conflicts: [] } };