import type { Meta, StoryObj } from "@storybook/nextjs";
import { DataTable } from "./data-table";

const meta: Meta<typeof DataTable> = { title: "Shared/DataTable", component: DataTable, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof DataTable>;

const rows = [
  { id: 1, name: "Sarah Lee", role: "Designer", score: 92 },
  { id: 2, name: "John Park", role: "Engineer", score: 71 },
  { id: 3, name: "Anna Sun", role: "PM", score: 84 },
];

export const Default: Story = {
  args: {
    columns: [
      { key: "name", label: "Name" },
      { key: "role", label: "Role" },
      { key: "score", label: "Score" },
    ],
    rows,
  },
};
export const Empty: Story = {
  args: {
    columns: [
      { key: "name", label: "Name" },
      { key: "role", label: "Role" },
    ],
    rows: [],
  },
};