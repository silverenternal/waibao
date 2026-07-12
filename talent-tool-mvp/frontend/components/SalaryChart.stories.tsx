import type { Meta, StoryObj } from "@storybook/nextjs";
import SalaryChart from "./SalaryChart";

const meta: Meta<typeof SalaryChart> = { title: "Components/SalaryChart", component: SalaryChart, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof SalaryChart>;

export const Default: Story = { args: { data: [{ role: "Junior", salary: 60000 }, { role: "Mid", salary: 90000 }, { role: "Senior", salary: 130000 }] } };
export const Empty: Story = { args: { data: [] } };