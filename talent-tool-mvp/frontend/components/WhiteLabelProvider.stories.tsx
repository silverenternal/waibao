import type { Meta, StoryObj } from "@storybook/nextjs";
import WhiteLabelProvider from "./WhiteLabelProvider";
import { DEFAULT_BRANDING } from "../lib/theme";

const meta: Meta<typeof WhiteLabelProvider> = {
  title: "Components/WhiteLabelProvider",
  component: WhiteLabelProvider,
  tags: ["autodocs"],
};
export default meta;

type Story = StoryObj<typeof WhiteLabelProvider>;

const CUSTOM_BRAND = {
  ...DEFAULT_BRANDING,
  product_name: "Acme Talent Cloud",
  primary_color: "#FF6B35",
  secondary_color: "#1B1B3A",
  accent_color: "#FFE066",
  font_family: "Inter",
  hide_powered_by: false,
};

export const Default: Story = {
  args: {
    initialBranding: DEFAULT_BRANDING,
    skipFetch: true,
    children: <div className="p-4">默认 Waibao 品牌</div>,
  },
};

export const AcmeBranding: Story = {
  args: {
    initialBranding: CUSTOM_BRAND,
    skipFetch: true,
    children: (
      <div
        className="p-4"
        style={{
          background: "var(--color-secondary)",
          color: "white",
          fontFamily: "var(--font-family)",
        }}
      >
        <h2 style={{ color: "var(--color-primary)" }}>
          {CUSTOM_BRAND.product_name}
        </h2>
        <p style={{ color: "var(--color-accent)" }}>这是客户定制品牌的预览。</p>
      </div>
    ),
  },
};