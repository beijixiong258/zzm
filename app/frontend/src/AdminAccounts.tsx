import type { User } from "./types";
import AccessSettings from "./AccessSettings";
import GlobalAccounts from "./GlobalAccounts";

export default function AdminAccounts({
  user,
  onChanged,
}: {
  user: User;
  onChanged?: () => void;
}) {
  if (user.role !== "admin")
    return (
      <p>
        Global account administration is available only to active
        administrators.
      </p>
    );
  return (
    <div className="account-management">
      <AccessSettings key={user.id} />
      <GlobalAccounts user={user} onChanged={onChanged} />
    </div>
  );
}
