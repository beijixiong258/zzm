import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import Profile from "../src/Profile";
import Feedback from "../src/Feedback";
import Avatar from "../src/Avatar";
import { api } from "../src/api";
import { confirmNavigation, hasUnsavedChanges } from "../src/navigation-guard";
import type { User } from "../src/types";
import "../src/styles.css";
import "../src/stage2.css";
import "../src/design-tokens.css";
import "../src/contrast.css";
declare global {
  interface Window {
    stage9Dirty: () => boolean;
  }
}
window.stage9Dirty = hasUnsavedChanges;
function Harness() {
  const [user, setUser] = useState<User | null>(null);
  const [page, setPage] = useState<"account" | "feedback">(() =>
    sessionStorage.getItem("stage9-fixture-page") === "feedback"
      ? "feedback"
      : "account",
  );
  useEffect(() => {
    sessionStorage.setItem("stage9-fixture-page", page);
  }, [page]);
  useEffect(() => {
    void api.me().then((result) => setUser(result.user));
  }, []);
  async function switchUser(id: string) {
    await fetch(`/fixture/account/${id}`, { method: "POST" });
    setUser((await api.me()).user);
  }
  if (!user) return <p>Loading synthetic fixture…</p>;
  return (
    <>
      <header
        style={{
          padding: "16px",
          display: "flex",
          gap: "12px",
          flexWrap: "wrap",
          background: "#eef4ef",
        }}
      >
        <strong>Synthetic UI fixture — not FastAPI evidence</strong>
        <Avatar user={user} />
        <button
          onClick={() => {
            if (confirmNavigation()) setPage("account");
          }}
        >
          Account fixture
        </button>
        <button
          onClick={() => {
            if (confirmNavigation()) setPage("feedback");
          }}
        >
          Feedback fixture
        </button>
        <label>
          Fixture account
          <select
            aria-label="Fixture account"
            value={user.id}
            onChange={(e) => void switchUser(e.target.value)}
          >
            <option value="student-a">Student A</option>
            <option value="student-b">Student B</option>
            <option value="admin">Administrator</option>
          </select>
        </label>
      </header>
      {page === "account" ? (
        <Profile user={user} onUpdate={setUser} />
      ) : (
        <Feedback user={user} />
      )}
    </>
  );
}
createRoot(document.getElementById("root")!).render(<Harness />);
