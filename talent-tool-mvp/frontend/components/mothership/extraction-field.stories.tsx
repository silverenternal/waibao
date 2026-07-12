import type { Meta, StoryObj } from "@storybook/nextjs";
import { ExtractionField } from "./extraction-field";

const meta: Meta<typeof ExtractionField> = { title: "Mothership/ExtractionField", component: ExtractionField, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof ExtractionField>;

export const Confident: Story = { args: { label: "Years experience", value: "8", confidence: 0.95 } };
export const Uncertain: Story = { args: { label: "Salary expectation", value: "Unknown", confidence: 0.32 } };