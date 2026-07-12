import type { Meta, StoryObj } from "@storybook/nextjs";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "./table";

const meta: Meta<typeof Table> = { title: "UI/Table", component: Table, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof Table>;

export const Default: Story = {
  render: () => (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Role</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        <TableRow>
          <TableCell>Sarah Lee</TableCell>
          <TableCell>Designer</TableCell>
          <TableCell>Active</TableCell>
        </TableRow>
        <TableRow>
          <TableCell>John Park</TableCell>
          <TableCell>Engineer</TableCell>
          <TableCell>Paused</TableCell>
        </TableRow>
      </TableBody>
    </Table>
  ),
};