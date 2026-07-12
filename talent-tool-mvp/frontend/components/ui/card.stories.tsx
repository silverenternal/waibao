import type { Meta, StoryObj } from "@storybook/nextjs";
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from "./card";

const meta: Meta<typeof Card> = {
  title: "UI/Card",
  component: Card,
  tags: ["autodocs"],
};
export default meta;

type Story = StoryObj<typeof Card>;

export const Basic: Story = {
  render: () => (
    <Card className="w-[350px]">
      <CardHeader>
        <CardTitle>Candidate — Sarah Lee</CardTitle>
      </CardHeader>
      <CardContent>
        <p>Senior product designer with 8 years of experience.</p>
      </CardContent>
      <CardFooter>
        <span>Score: 92</span>
      </CardFooter>
    </Card>
  ),
};

export const WithoutFooter: Story = {
  render: () => (
    <Card className="w-[350px]">
      <CardHeader>
        <CardTitle>Quick card</CardTitle>
      </CardHeader>
      <CardContent>Body content only.</CardContent>
    </Card>
  ),
};