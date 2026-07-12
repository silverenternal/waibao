import type { Meta, StoryObj } from "@storybook/nextjs";
import { KanbanBoard } from "./kanban-board";

const meta: Meta<typeof KanbanBoard> = { title: "Shared/KanbanBoard", component: KanbanBoard, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof KanbanBoard>;

export const Default: Story = {
  args: {
    columns: [
      { id: "todo", title: "To do", items: [{ id: "1", title: "Review Sarah" }] },
      { id: "doing", title: "In progress", items: [{ id: "2", title: "Interview John" }] },
      { id: "done", title: "Done", items: [{ id: "3", title: "Hired Anna" }] },
    ],
  },
};