import type { Meta, StoryObj } from "@storybook/nextjs";
import { CvUploadZone } from "./cv-upload-zone";

const meta: Meta<typeof CvUploadZone> = { title: "Mothership/CvUploadZone", component: CvUploadZone, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof CvUploadZone>;

export const Default: Story = { args: {} };
export const Uploading: Story = { args: { status: "uploading" } };
export const Error: Story = { args: { status: "error" } };