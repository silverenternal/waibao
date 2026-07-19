import { JobseekerProfileClient } from "./_client";

/**
 * v9.1 · 求职者 Profile page (server component, thin wrapper).
 *
 * Metadata + noindex directives come from the segment layout
 * (app/jobseeker/profile/layout.tsx → generatePrivacyMetadata). The
 * interactive OpenResume UI lives in _client.tsx and is extended in v11.2
 * (T6305) with a 身份与版本 card linking to /jobseeker/identity.
 */
export default function JobseekerProfilePage() {
  return <JobseekerProfileClient />;
}
