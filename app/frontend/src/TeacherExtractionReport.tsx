import type { ExtractionReport } from "./types";
export default function TeacherExtractionReport({
  report,
}: {
  report: ExtractionReport;
}) {
  return (
    <>
      {report.truncated && (
        <p className="tw-warning" role="status">
          Extraction was truncated. Inspect the original file.
        </p>
      )}
      {report.visual_review_required && (
        <p className="tw-warning" role="status">
          Visual review required · check figures against the original.
        </p>
      )}
      {!!report.failed_units.length && (
        <p className="tw-warning" role="status">
          {report.failed_units.length}{" "}
          {report.failed_units.length === 1 ? "part" : "parts"} could not be
          extracted. Check coverage details.
        </p>
      )}
      <details className="tw-extraction">
        <summary>Extraction coverage · {report.method}</summary>
        <p>
          Processed {report.units_processed} of {report.units_total} parts · OCR
          on {report.ocr_units} · {report.images_detected} images detected.
        </p>
        <p>
          {report.chars_extracted.toLocaleString("en-US")} characters extracted
          · {report.excerpt_chars.toLocaleString("en-US")} available as excerpt.
        </p>
        {!!report.failed_units.length && (
          <ul>
            {report.failed_units.map((text, i) => (
              <li key={i}>{text}</li>
            ))}
          </ul>
        )}
        {!!report.notes.length && (
          <ul>
            {report.notes.map((text, i) => (
              <li key={i}>{text}</li>
            ))}
          </ul>
        )}
      </details>
    </>
  );
}
