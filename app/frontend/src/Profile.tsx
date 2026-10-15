import { useEffect, useRef, useState, type FormEvent } from "react";
import { useUnsavedChanges } from "./navigation-guard";
import { api } from "./api";
import type { User } from "./types";
import { useUiText } from "./uiText";
import Avatar, { avatarPreview, verifyAvatarImage } from "./Avatar";

import { ErrorBanner, Notice, errorMessage } from "./ui";
export default function Profile(props: {
  user: User;
  onUpdate: (u: User) => void;
}) {
  return <AccountProfile key={props.user.id} {...props} />;
}
function AccountProfile({
  user,
  onUpdate,
}: {
  user: User;
  onUpdate: (u: User) => void;
}) {
  const { t } = useUiText();
  const [name, setName] = useState(user.name),
    [current, setCurrent] = useState(""),
    [next, setNext] = useState(""),
    [repeat, setRepeat] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [success, setSuccess] = useState("");
  const alive = useRef(true);
  const [candidate, setCandidate] = useState<{
    file: File;
    preview: string;
  } | null>(null);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [avatarError, setAvatarError] = useState("");
  const [avatarSuccess, setAvatarSuccess] = useState("");
  const [avatarPending, setAvatarPending] = useState<{
    url: string | null;
    action: "upload" | "remove";
  } | null>(null);
  const [avatarUnknown, setAvatarUnknown] = useState(false);
  const avatarGeneration = useRef(0);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const demo = user.is_demo === true;
  useUnsavedChanges(
    name !== user.name ||
      !!current ||
      !!next ||
      !!repeat ||
      busy ||
      !!candidate ||
      avatarBusy ||
      !!avatarPending ||
      avatarUnknown,
  );
  const accountBusy = busy || avatarBusy || !!avatarPending;
  async function selectAvatar(file?: File) {
    if (!file || accountBusy) return;
    const generation = ++avatarGeneration.current;
    setAvatarBusy(true);
    setAvatarError("");
    setAvatarSuccess("");
    try {
      const preview = await avatarPreview(file);
      if (alive.current && generation === avatarGeneration.current)
        setCandidate({ file, preview });
    } catch (e) {
      if (alive.current && generation === avatarGeneration.current)
        setAvatarError(errorMessage(e));
    } finally {
      if (alive.current && generation === avatarGeneration.current)
        setAvatarBusy(false);
    }
  }
  async function readAvatar(expected: {
    url: string | null;
    action: "upload" | "remove";
  }) {
    if (
      (expected.action === "upload" && !expected.url) ||
      (expected.action === "remove" && expected.url !== null)
    )
      throw new Error(
        "The avatar response did not match the requested change.",
      );
    const verified = (await api.me()).user;
    if (verified.id !== user.id || verified.avatar_url !== expected.url)
      throw new Error(
        "The saved avatar could not be verified. Check the saved result again.",
      );
    if (expected.url) await verifyAvatarImage(expected.url);
    if (!alive.current) return;
    // Updating the projection never resets unrelated local name/password edits.
    onUpdate(verified);
    setCandidate(null);
    setAvatarPending(null);
    setAvatarUnknown(false);
    setAvatarSuccess(
      expected.action === "remove"
        ? "Avatar removed and verified."
        : "Avatar saved and verified.",
    );
  }
  async function saveAvatar(action: "upload" | "remove", checkOnly = false) {
    if (busy || avatarBusy || (!checkOnly && avatarPending)) return;
    if (action === "upload" && !candidate && !checkOnly) return;
    setAvatarBusy(true);
    setAvatarError("");
    setAvatarSuccess("");
    let expected = avatarPending;
    try {
      if (!checkOnly) {
        const result =
          action === "remove"
            ? await api.removeAvatar()
            : await api.uploadAvatar(candidate!.file);
        if (!alive.current) return;
        expected = { url: result.user.avatar_url ?? null, action };
        setAvatarPending(expected);
        setAvatarUnknown(false);
        if (
          result.user.id !== user.id ||
          (action === "upload" && !expected.url) ||
          (action === "remove" && expected.url !== null)
        )
          throw new Error(
            "The avatar response did not match the requested change.",
          );
      }
      if (expected) await readAvatar(expected);
    } catch (e) {
      if (!alive.current) return;
      if (!expected) setAvatarUnknown(true);
      setAvatarError(
        `${expected ? "The change was accepted, but verification is incomplete. " : "The change could not be confirmed. Your preview has been kept. "}${errorMessage(e)}`,
      );
    } finally {
      if (alive.current) setAvatarBusy(false);
    }
  }
  async function reloadAvatar() {
    if (accountBusy) return;
    setAvatarBusy(true);
    setAvatarError("");
    setAvatarSuccess("");
    try {
      const verified = (await api.me()).user;
      if (verified.id !== user.id)
        throw new Error("The current account changed.");
      if (verified.avatar_url) await verifyAvatarImage(verified.avatar_url);
      if (alive.current) {
        onUpdate(verified);
        setAvatarUnknown(false);
        setAvatarSuccess(
          "Current saved avatar loaded. Your unsaved preview has not been applied.",
        );
      }
    } catch (e) {
      if (alive.current) setAvatarError(errorMessage(e));
    } finally {
      if (alive.current) setAvatarBusy(false);
    }
  }
  async function save(e: FormEvent, password = false) {
    e.preventDefault();
    if (accountBusy) return;
    setError("");
    setSuccess("");
    if (password && (next !== repeat || next === current)) {
      setError(
        next !== repeat
          ? t("passwordMismatch")
          : "Choose a password different from your current password.",
      );
      return;
    }
    setBusy(true);
    try {
      if (password) await api.changePassword(current, next);
      else await api.profile(name.trim());
      const verified = (await api.me()).user;
      if (!password && verified.name !== name.trim())
        throw new Error("Saved name could not be verified.");
      if (!alive.current) return;
      onUpdate(verified);
      if (!password) setName(verified.name);
      else {
        setCurrent("");
        setNext("");
        setRepeat("");
      }
      setSuccess(t("saved"));
    } catch (e) {
      if (alive.current) setError(errorMessage(e));
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  return (
    <div className="page profile-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">AIcademiya · {t(user.role)}</div>
          <h1>Account</h1>
          <p>{user.email}</p>
        </div>
        <Avatar user={user} large />
      </div>
      <ErrorBanner error={error} />
      {success && <Notice>{success}</Notice>}
      <section
        className="card form-card account-avatar-editor"
        aria-labelledby="account-avatar-title"
      >
        <h2 id="account-avatar-title">Profile avatar</h2>
        <p>
          Visible to signed-in users only. Choose a local image, then save your
          preview.
        </p>
        <ErrorBanner error={avatarError} />
        {avatarSuccess && (
          <div role="status">
            <Notice>{avatarSuccess}</Notice>
          </div>
        )}
        {avatarBusy && <p role="status">Preparing or verifying your avatar…</p>}
        <div className="account-avatar-layout">
          {candidate && (
            <figure className="account-avatar-preview">
              <img
                src={candidate.preview}
                width={256}
                height={256}
                alt="Unsaved centered avatar preview"
              />
              <figcaption>Unsaved preview · 256 × 256</figcaption>
            </figure>
          )}
          <div className="account-avatar-controls">
            <label>
              Choose avatar image
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                disabled={accountBusy}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  void selectAvatar(file);
                }}
              />
            </label>
            <small>
              Static PNG, JPEG or WebP · up to 5 MiB and 16 million pixels.
              Centered square crop. The server strips metadata and saves a 256 ×
              256 PNG; the original is not retained.
            </small>
            <div className="account-avatar-actions">
              <button
                className="primary"
                type="button"
                disabled={accountBusy || !candidate}
                onClick={() => void saveAvatar("upload")}
              >
                Save avatar
              </button>
              {candidate && (
                <button
                  className="secondary"
                  type="button"
                  disabled={accountBusy}
                  onClick={() => {
                    setCandidate(null);
                    setAvatarError("");
                  }}
                >
                  Discard preview
                </button>
              )}
              <button
                className="secondary"
                type="button"
                disabled={accountBusy || !user.avatar_url}
                onClick={() => void saveAvatar("remove")}
              >
                Remove avatar
              </button>
              {avatarPending && (
                <button
                  className="secondary"
                  type="button"
                  disabled={busy || avatarBusy}
                  onClick={() => void saveAvatar(avatarPending.action, true)}
                >
                  Check saved avatar
                </button>
              )}
              {avatarUnknown && !avatarPending && (
                <button
                  className="secondary"
                  type="button"
                  disabled={accountBusy}
                  onClick={() => void reloadAvatar()}
                >
                  Reload current avatar
                </button>
              )}
            </div>
          </div>
        </div>
      </section>
      <div className="teacher-editor-grid">
        <section className="card form-card">
          <h2>{"Display name"}</h2>
          <p>{"Your login email and role do not change."}</p>
          <form onSubmit={(e) => void save(e)}>
            <label>
              {t("name")}
              <input
                value={name}
                disabled={accountBusy}
                required
                maxLength={100}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <button
              className="primary"
              disabled={accountBusy || !name.trim() || name === user.name}
            >
              {t("save")}
            </button>
          </form>
        </section>
        <section className="card form-card">
          <h2>{"Change password"}</h2>
          {demo ? (
            <p>{"Synthetic demo accounts cannot change passwords."}</p>
          ) : (
            <form onSubmit={(e) => void save(e, true)}>
              <label>
                {"Current password"}
                <input
                  type="password"
                  required
                  autoComplete="current-password"
                  disabled={accountBusy}
                  value={current}
                  onChange={(e) => setCurrent(e.target.value)}
                />
              </label>
              <label>
                {t("newPassword")}
                <input
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={8}
                  maxLength={512}
                  pattern="(?=.*[A-Za-z])(?=.*[0-9]).{8,512}"
                  disabled={accountBusy}
                  value={next}
                  onChange={(e) => setNext(e.target.value)}
                />
              </label>
              <label>
                {t("repeatPassword")}
                <input
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={8}
                  maxLength={512}
                  disabled={accountBusy}
                  value={repeat}
                  onChange={(e) => setRepeat(e.target.value)}
                />
              </label>
              <small>
                {
                  "8–512 characters with a letter and a digit. Other sessions will be signed out."
                }
              </small>
              <button
                className="primary"
                disabled={accountBusy || !current || !next || next !== repeat}
              >
                {t("save")}
              </button>
            </form>
          )}
        </section>
      </div>
    </div>
  );
}
