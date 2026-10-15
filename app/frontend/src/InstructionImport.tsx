import { useEffect, useRef, useState } from "react";
import { FileUp } from "lucide-react";
import { api } from "./api";
import { errorMessage } from "./ui";
import TeacherExtractionReport from "./TeacherExtractionReport";
import {
  combineInstructions,
  instructionLimit,
} from "./teacher-workbench-import";
import "./teacher-workbench.css";
type ImportResult = Awaited<ReturnType<typeof api.instructionPreview>>;
export default function InstructionImport({
  sid,
  instructions,
  disabled,
  onApply,
}: {
  sid: string;
  instructions: string;
  disabled?: boolean;
  onApply: (text: string) => void;
}) {
  const [open, setOpen] = useState(false),
    [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null),
    [text, setText] = useState("");
  const [unadopted, setUnadopted] = useState<ImportResult | null>(null);
  const [error, setError] = useState(""),
    [mode, setMode] = useState<"append" | "replace">("append");
  const request = useRef(0),
    edits = useRef(0),
    dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (open) dialog.current?.showModal();
  }, [open]);
  useEffect(
    () => () => {
      request.current++;
    },
    [sid],
  );
  function close() {
    request.current++;
    setBusy(false);
    setOpen(false);
  }
  async function extract(file: File) {
    const token = ++request.current,
      edit = edits.current;
    setBusy(true);
    setError("");
    setUnadopted(null);
    try {
      const next = await api.instructionPreview(sid, file);
      if (token !== request.current) return;
      if (next.status === "error") {
        setError(
          next.warning ||
            "Extraction failed. Your review text and teacher draft are unchanged.",
        );
        setUnadopted(next);
        return;
      }
      if (edit === edits.current) {
        setResult(next);
        setText(next.text);
      } else setUnadopted(next);
    } catch (e) {
      if (token === request.current) setError(errorMessage(e));
    } finally {
      if (token === request.current) setBusy(false);
    }
  }
  const combined = combineInstructions(instructions, text, mode);
  const limit = Math.min(
    instructionLimit,
    result?.max_instruction_chars ?? instructionLimit,
  );
  const over = combined.length > limit;
  return (
    <div className="tw-import">
      <button
        className="secondary"
        disabled={disabled}
        onClick={() => setOpen(true)}
      >
        <FileUp size={16} />
        Import instructions
      </button>
      {open && (
        <dialog
          ref={dialog}
          className="tw-dialog tw-import-dialog"
          aria-labelledby="tw-import-title"
          onCancel={close}
        >
          <h2 id="tw-import-title">Import instructions</h2>
          <p>
            Review the text against the original. Apply changes only the unsaved
            draft; it does not save or publish.
          </p>
          <label>
            Choose instruction file
            <input
              type="file"
              accept=".txt,.doc,.docx,.pdf,.ppt,.pptx,.md"
              disabled={disabled}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void extract(file);
                e.target.value = "";
              }}
            />
          </label>
          {busy && (
            <p role="status">Extracting… Your review edits will be kept.</p>
          )}
          {error && (
            <p className="tw-warning" role="alert">
              {error} Existing edits are unchanged.
            </p>
          )}
          {unadopted && (
            <div className="tw-warning">
              <p>
                Extraction returned for {unadopted.filename}; your newer review
                edits were kept.
              </p>
              {unadopted.warning && <p>{unadopted.warning}</p>}
              <TeacherExtractionReport report={unadopted.extraction_report} />
              {unadopted.status !== "error" && (
                <button
                  className="secondary"
                  onClick={() => {
                    setResult(unadopted);
                    setText(unadopted.text);
                    edits.current++;
                    setUnadopted(null);
                  }}
                >
                  Use extracted text instead of review edits
                </button>
              )}
            </div>
          )}
          {result && (
            <>
              <p>
                <strong>{result.filename}</strong> · {result.status}
              </p>
              {result.warning && (
                <p className="tw-warning" role="status">
                  {result.warning}
                </p>
              )}
              <TeacherExtractionReport report={result.extraction_report} />
            </>
          )}
          <label>
            Review extracted instructions
            <textarea
              rows={9}
              value={text}
              onChange={(e) => {
                edits.current++;
                setText(e.target.value);
              }}
            />
          </label>
          <fieldset className="tw-import-mode">
            <legend>Apply to instructions</legend>
            <label>
              <input
                type="radio"
                name="tw-import-mode"
                checked={mode === "append"}
                onChange={() => setMode("append")}
              />
              Append to instructions
            </label>
            <label>
              <input
                type="radio"
                name="tw-import-mode"
                checked={mode === "replace"}
                onChange={() => setMode("replace")}
              />
              Replace instructions
            </label>
          </fieldset>
          <p aria-live="polite">
            Result: {combined.length.toLocaleString("en-US")} /{" "}
            {limit.toLocaleString("en-US")} characters.
          </p>
          {mode === "replace" && (
            <p className="tw-warning">
              Replace removes the current field text only when you explicitly
              Apply.
            </p>
          )}
          {over && (
            <p role="alert" className="tw-warning">
              Combined instructions exceed the limit. Edit or trim the review
              text; nothing is silently truncated.
            </p>
          )}
          <details>
            <summary>Resulting instructions</summary>
            <pre className="tw-exact-text">{combined}</pre>
          </details>
          <div className="button-row">
            <button className="secondary" onClick={close}>
              Cancel
            </button>
            <button
              className="primary"
              disabled={disabled || busy || !result || !text.trim() || over}
              onClick={() => {
                onApply(combined);
                close();
              }}
            >
              Apply to unsaved draft
            </button>
          </div>
        </dialog>
      )}
    </div>
  );
}
