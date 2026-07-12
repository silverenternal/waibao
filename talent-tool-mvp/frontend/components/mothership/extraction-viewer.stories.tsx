import type { Meta, StoryObj } from "@storybook/nextjs";
import { ExtractionViewer } from "./extraction-viewer";

const meta: Meta<typeof ExtractionViewer> = { title: "Mothership/ExtractionViewer", component: ExtractionViewer, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof ExtractionViewer>;

export const Default: Story = {
  args: { fields: [{ label: "Name", value: "Sarah Lee", confidence: 0.98 }, { label: "Role", value: "Senior Designer", confidence: 0.9 }] },
};