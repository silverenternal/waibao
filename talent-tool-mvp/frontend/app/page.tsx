import { redirect } from "next/navigation";
import type { Metadata } from "next";
import { generatePageMetadata, faqJsonLd } from "@/lib/metadata";
import { JsonLd } from "@/components/JsonLd";

export const metadata: Metadata = generatePageMetadata({
  title: "AI-Powered Talent Platform",
  description:
    "RecruitTech unifies candidate matching, copilot dashboards, and multi-persona workflows in one AI-powered talent platform.",
  path: "/",
  isHome: true,
  jsonLd: [
    faqJsonLd([
      {
        question: "What is RecruitTech?",
        answer:
          "RecruitTech is an AI-powered talent platform that automates candidate matching, screening and outreach for staffing agencies and in-house talent teams.",
      },
      {
        question: "Who is RecruitTech for?",
        answer:
          "In-house talent partners, recruitment agencies, and hiring managers who want to reduce time-to-hire and improve match quality.",
      },
      {
        question: "Does RecruitTech integrate with my ATS?",
        answer:
          "Yes — RecruitTech supports Bullhorn, HubSpot, Greenhouse, Workday and a generic REST adapter out of the box.",
      },
    ]),
  ],
});

export default function HomePage() {
  return (
    <>
      <JsonLd
        data={[
          {
            "@context": "https://schema.org",
            "@type": "WebSite",
            name: "RecruitTech",
            url: "https://recruittech.example.com",
            potentialAction: {
              "@type": "SearchAction",
              target:
                "https://recruittech.example.com/search?q={search_term_string}",
              "query-input": "required name=search_term_string",
            },
          },
        ]}
        id="jsonld-home-website"
      />
      <>{redirect("/login")}</>
    </>
  );
}
