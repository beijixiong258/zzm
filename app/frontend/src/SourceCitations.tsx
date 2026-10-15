import { BookOpen, ExternalLink } from "lucide-react";
import "./web-search.css";
import { useUiText } from "./uiText";
import type { Message } from "./types";
import "./document-reader.css";

export default function SourceCitations({
  citations,
}: {
  citations: Message["citations"];
}) {
  const { t } = useUiText();
  if (!citations?.length) return null;
  const isWeb = (c: NonNullable<Message["citations"]>[number]) =>
    c.kind !== "document" && c.kind !== "document_supplement" && !!c.url && /^https?:\/\//i.test(c.url);
  const web = citations.filter(isWeb);
  return (
    <div className="citations">
      {citations
        .filter((c) => c.kind === "document")
        .map((c, i) => {
          const prefix = c.material_id
            ? `/api/materials/${encodeURIComponent(c.material_id)}/preview`
            : "";
          const renderedPrefix = c.material_id ? `/api/materials/${encodeURIComponent(c.material_id)}/document/pdf` : "";
          let rendered = false;
          if (renderedPrefix && c.url?.startsWith(renderedPrefix + "?") && c.revision_id) {
            const candidate = new URL(c.url, "http://source.invalid");
            rendered = candidate.pathname === renderedPrefix && candidate.searchParams.get("revision_id") === c.revision_id && candidate.searchParams.get("version_id") === (c.version_id ?? null);
          }
          const url =
            prefix &&
            c.url &&
            (rendered || c.url.startsWith(prefix + "?") ||
              c.url.startsWith(prefix + "#") ||
              c.url === prefix)
              ? c.url
              : null;
          return (
            <section
              className="document-citation"
              key={i}
              aria-label="Document source citation"
            >
              <strong>
                <BookOpen size={12} /> {c.source_label}
              </strong>
              <small>
                {rendered ? "Rendered page" : "PDF page"} {c.page}
                {c.printed_label ? ` · printed ${c.printed_label}` : ""}
                {c.evidence_kind === "source_image" ? " · Original page image" : c.block_id ? ` · block ${c.block_id}` : ""}
                {" · revision "}{c.revision_id}
              </small>
              {(c.quote || c.text) && (
                <blockquote>{c.quote ?? c.text}</blockquote>
              )}
              {url ? (
                <a href={url} target="_blank" rel="noopener noreferrer">
                  <ExternalLink size={13} /> {rendered ? "Open cited rendered page" : "Open cited original page"}
                </a>
              ) : (
                <small>Original-page link unavailable.</small>
              )}
            </section>
          );
        })}
      {citations.filter((c) => c.kind === "document_supplement").map((c, i) => {
        const path = c.material_id && c.supplement_id ? `/api/materials/${encodeURIComponent(c.material_id)}/document/supplements/${encodeURIComponent(c.supplement_id)}/text` : "";
        let url: string | null = null;
        if (path && c.revision_id && c.url?.startsWith(path + "?")) {
          const candidate = new URL(c.url, "http://source.invalid");
          if (candidate.pathname === path && candidate.searchParams.get("revision_id") === c.revision_id && candidate.searchParams.get("version_id") === (c.version_id ?? null)) url = c.url;
        }
        return <section className="document-citation" key={`supplement-${i}`} aria-label="Supplementary source citation">
          <strong><BookOpen size={12} /> {c.source_label}</strong>
          <small>{c.source_kind?.replaceAll("_", " ")} · {c.source_part} · revision {c.revision_id}</small>
          {(c.quote || c.text) && <blockquote>{c.quote ?? c.text}</blockquote>}
          {url ? <a href={url} target="_blank" rel="noopener noreferrer"><ExternalLink size={13} /> Open cited source note</a> : <small>Source-note link unavailable.</small>}
        </section>;
      })}
      {citations
        .filter((c) => c.kind !== "document" && c.kind !== "document_supplement" && !isWeb(c))
        .map((c, i) => (
          <details key={i}>
            <summary>
              <BookOpen size={12} />
              {c.source_label}
            </summary>
            {c.text && <p>{c.text}</p>}
          </details>
        ))}
      {!!web.length && (
        <section className="web-sources" aria-label={t("retrievedWebSources")}>
          <h4>{t("retrievedWebSources")}</h4>
          {web.map((c, i) => (
            <div className="web-source" key={i}>
              <a
                className="web-source-link"
                href={c.url}
                title={c.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                <ExternalLink size={13} />
                {c.source_label}
              </a>
              {c.text && (
                <details>
                  <summary>{t("sourceExcerpt")}</summary>
                  <p>{c.text}</p>
                </details>
              )}
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
