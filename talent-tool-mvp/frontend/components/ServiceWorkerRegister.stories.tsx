import type { Meta, StoryObj } from "@storybook/nextjs";
import ServiceWorkerRegister from "./ServiceWorkerRegister";

const meta: Meta<typeof ServiceWorkerRegister> = { title: "Components/ServiceWorkerRegister", component: ServiceWorkerRegister, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof ServiceWorkerRegister>;

export const Default: Story = { args: {} };