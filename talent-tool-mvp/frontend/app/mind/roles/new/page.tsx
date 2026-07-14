import { ErrorBoundary } from "@/components/ErrorBoundary";
import { RoleWizard } from "@/components/mind/role-wizard";

export default function NewRolePage() {
  return (
    <ErrorBoundary>(<div className="mx-auto max-w-2xl py-4">
        <RoleWizard />
      </div>)</ErrorBoundary>
  );
}
