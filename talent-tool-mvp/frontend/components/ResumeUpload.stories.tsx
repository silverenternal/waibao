import type { Meta, StoryObj } from "@storybook/nextjs";
import ResumeUpload from "./ResumeUpload";

const meta: Meta<typeof ResumeUpload> = { title: "Components/ResumeUpload", component: ResumeUpload, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof ResumeUpload>;

export const Default: Story = { args: {} };
export const Uploading: Story = { args: { status: "uploading" } };