import type { Meta, StoryObj } from "@storybook/nextjs";
import { SkillChips } from "./skill-chips";

const meta: Meta<typeof SkillChips> = { title: "Shared/SkillChips", component: SkillChips, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof SkillChips>;

export const Default: Story = { args: { skills: ["React", "TypeScript", "GraphQL", "Node.js"] } };
export const FewSkills: Story = { args: { skills: ["Python"] } };
export const Empty: Story = { args: { skills: [] } };