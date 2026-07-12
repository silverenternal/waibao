import type { Meta, StoryObj } from "@storybook/nextjs";
import AssessmentReport from "./AssessmentReport";

const meta: Meta<typeof AssessmentReport> = { title: "Components/AssessmentReport", component: AssessmentReport, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof AssessmentReport>;

export const Default: Story = { args: { candidate: "Sarah Lee", overall: 87, sections: [{ name: "Cognitive", score: 90 }, { name: "Personality", score: 84 }] } };