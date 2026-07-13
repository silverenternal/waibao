import type { Meta, StoryObj } from "@storybook/react"
import { ResourceTable } from "./ResourceTable"
import type { ColumnDef } from "@tanstack/react-table"

interface Row {
  id: string
  name: string
  status: string
  count: number
}

const data: Row[] = [
  { id: "1", name: "matching-feedback", status: "enabled", count: 12 },
  { id: "2", name: "bias-impact", status: "beta", count: 5 },
  { id: "3", name: "tone-learning", status: "enabled", count: 9 },
  { id: "4", name: "ps-detect", status: "maintenance", count: 0 },
]

const cols: ColumnDef<Row>[] = [
  { id: "name", header: "Name", cell: ({ row }) => row.original.name },
  { id: "status", header: "Status", cell: ({ row }) => row.original.status },
  {
    id: "count",
    header: "Count",
    cell: ({ row }) => row.original.count,
  },
]

const meta: Meta<typeof ResourceTable<Row>> = {
  title: "Admin/ResourceTable",
  component: ResourceTable as any,
  tags: ["autodocs"],
}
export default meta

type Story = StoryObj<typeof ResourceTable<Row>>

export const Default: Story = {
  args: { data, columns: cols, resource: "test" },
}
