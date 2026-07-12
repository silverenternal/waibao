import type { Meta, StoryObj } from "@storybook/nextjs";
import JsonLd from "./JsonLd";

const meta: Meta<typeof JsonLd> = { title: "Components/JsonLd", component: JsonLd, tags: ["autodocs"] };
export default meta;
type Story = StoryObj<typeof JsonLd>;

export const Organization: Story = { args: { data: { "@context": "https://schema.org", "@type": "Organization", name: "RecruitTech" } } };