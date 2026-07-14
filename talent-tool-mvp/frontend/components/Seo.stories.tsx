import type { Meta, StoryObj } from "@storybook/nextjs";
import { Seo } from "./Seo";
import { SITE_URL } from "@/lib/metadata";

const meta: Meta<typeof Seo> = {
  title: "SEO/Seo",
  component: Seo,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj<typeof Seo>;

export const Breadcrumbs: Story = {
  render: () => (
    <Seo
      breadcrumbs={[
        { name: "Home", url: SITE_URL },
        { name: "Pricing", url: `${SITE_URL}/pricing` },
      ]}
    />
  ),
};

export const Faq: Story = {
  render: () => (
    <Seo
      faq={[
        { question: "Is there a free plan?", answer: "Yes, up to 50 candidates." },
        { question: "Do you support SSO?", answer: "SAML SSO on Business and above." },
      ]}
    />
  ),
};

export const JobPosting: Story = {
  render: () => (
    <Seo
      jobPosting={{
        title: "Senior Backend Engineer",
        description: "Build scalable recruitment pipelines.",
        datePosted: "2026-07-14",
        organizationName: "Acme Corp",
        organizationUrl: "https://acme.example.com",
        jobLocation: "London",
        employmentType: "FULL_TIME",
      }}
    />
  ),
};
