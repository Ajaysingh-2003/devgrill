import { ShieldAlert } from "lucide-react";
import { EmptyState } from "@devgrill/ui/components/devgrill/empty-state";
import { ApiError } from "@/lib/api";

/** What a console page shows when the API refuses (401/403); anything else is an error. */
export function refusal(response: Response | undefined, what: string) {
  if (response?.status === 401 || response?.status === 403) {
    return (
      <EmptyState icon={ShieldAlert} title={`${what} needs another role`}>
        Ask an admin to grant it in Users. Locally, add your GitHub login to ADMIN_GITHUB_LOGINS and sign in
        again.
      </EmptyState>
    );
  }
  throw new ApiError(response?.status ?? 503, null, response?.headers.get("x-request-id") ?? null);
}
