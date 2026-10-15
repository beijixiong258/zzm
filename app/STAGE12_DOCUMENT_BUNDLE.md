# Stage12 document bundle v1 — parser boundary

Purpose: a single-course end-to-end PDF upload → complete durable document → authorized reading → source citation. This file freezes the parser-to-application data boundary before independent implementation. No website deploy or existing model-service changes belong to the parser lane.

## Bundle directory

`manifest.json` UTF-8; raster pages under `pages/`, crops under `assets/`, optional raw parser evidence under `raw/`. All references relative, POSIX, no symlinks, no `..`, no credentials or original-user filesystem paths. Uploaded original remains separately owned by application; source_sha256 binds the output to exact input bytes. Raw extraction must survive corrections.

Manifest fields:
- `schema_version: 1`
- `source_sha256: string` (64 hex)
- `parser: {name:string, version:string, recipe:string}`
- `page_count: integer` total original PDF pages, not spreads' printed-page count
- `complete: boolean` true only when exact original page set is represented; readable blanks/figures are still pages. No silent page cap.
- `warnings: string[]`
- `pages: Page[]`, original order, every number1..page_count exactly once.

Page:
- `number:int` original one-based PDF page
- `printed_label:string|null`
- `rotation:int` clockwise rotation applied to original rendering, one of0/90/180/270
- `image:string` normalized full-page retained raster file, referenced boxes use this raster's orientation
- `width:int`, `height:int` raster pixel dimensions
- `status: text|blank|needs_review|failed`
- `issues:string[]`
- `blocks: Block[]` ordered by source reading order

Block:
- `id:string`, ASCII `p{number}-b{native_index}`; unique inside revision (nested printed captions receive distinct native indices or deterministic suffixes)
- `type: text|heading|list|table|image|caption|header|footer|page_number|equation|other`
- `bbox:[float,float,float,float]`, normalized x1,y1,x2,y2 in final retained page image
- `text:string` complete extracted text, not an excerpt; preserve original mistakes, blanks and exercise content
- `quality: extracted|needs_review|excluded`; extracted is machine transcription, NOT human-certified accuracy
- `issues:string[]`
- `assets:string[]` original crops, relative files
- `parent_id:string|null` binds image captions/footnotes to their parent; do not drop nested labels

Application owns source review/corrections/revision identity/author/timestamps and immutable course publication. Parser must not set reviewed/approved. Generated natural-image descriptions, ambiguous graph/table reconstructions, missing expected text or failed regions are `needs_review` and must not silently become authoritative teaching text. No promise to automatically detect all recognition errors. Preserve originals, raster and raw evidence when uncertain. Avoid hard-coded chapter answers or filename-specific success flags.

## Worker interface

Implement a task-local CLI accepting `--input PATH --output PATH`, optional explicit local VLM URL/device options discovered from actual runtime. Return a validated bundle (manifest and files). Parent integration will supply trusted source paths and a fresh output path; never overwrite an existing successful revision. Exit nonzero for failed/incomplete jobs, with retained receipt; preserve partial output but do not claim complete. Exact transport/queue is parent-owned.

This stage focuses full-document PDF. Existing supported Office/image/text flows remain compatible, with no claim that a PDF-only worker has solved every source format. A schema change requires a parent handoff before application wiring.

## Current infrastructure observation — do not use stale affinities

2026-10-10: GPU host now has32GB RAM, NUMA0 holds all memory, NUMA1 has0MB. Three teaching workers still report healthy with same router-config hash. Two T10 GPUs show13,457MiB used each; V100 reports0MiB but its worker is configured and active, so that does NOT authorize taking it over. Another llama-server on8027 exists. No stopping/restarting/retuning any existing process, router or service in the parser lane. First probe CPU-only, explicit no vision-projector GPU offload and current NUMA0 memory. Own loopback process may use18893 after listener check; close it on completion. Formal inference stays onUbuntu; Windows preparation/review allowed. No new model download is needed initially.
