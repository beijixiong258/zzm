# AIcademiya frontend

React + TypeScript + Vite. The website UI is **English-only**. There is no interface-language switch, and stored UI locale preferences are ignored. Teacher/student-authored names, teaching text, answers, source titles and course identifiers are displayed unchanged. `teaching_language` remains a curriculum setting, defaults to English on new sessions, and is not an interface locale.

## Development and build

```sh
npm ci --include=dev
npm run dev
npm test
npm run build
```

Vite binds `http://127.0.0.1:18774` and proxies `/api` to `http://127.0.0.1:18773` with cookie credentials. The production application calls real API endpoints; it does not import fixture data or silently replace provider failures with demo replies. `dist/` is the production build for same-origin backend hosting. Hash routes do not require server-side route rewriting.

The npm package is `aicademiya-frontend`. Search preferences use `aicademiya-search:<user>:<session>`; learning drafts use the existing scoped `aicademiya.draft.v1:` keys. No old-platform storage alias is read or migrated for the clean installation. Disabling UI locales does not clear any drafts or user content.

## Source responsibilities

- `src/App.tsx`: authentication, forced-password gate, role-aware navigation, profile entry and hash routes; document language is always English.
- `src/uiText.ts`: the single English UI-copy lookup. The obsolete translation context and dictionary module have been removed.
- `src/api.ts`, `types.ts`: HTTP/multipart contracts, version-aware reads/writes, cookie credentials and exports. Backend authorization remains authoritative.
- `src/LearningWorkspace.tsx`, `drafts.ts`, `study.ts`: dialogue/answer intents, scoped durable drafts, reading branches, reference/submission gates, read-only history and teacher observations.
- `src/TeacherSession.tsx`, `Authoring.tsx`, `WorksheetImport.tsx`: content drafts, groups/questions/images, source selection/removal, reviewed import and teaching language.
- `src/MaterialManager.tsx`, `Materials.tsx`: separate upload/Link controls, permissions, previews and archiving; native file input reset does not reset controlled dropdowns.
- `src/Versions.tsx`, `Availability.tsx`: immutable curriculum editions and readable comparisons; operational availability is independent of publication/restoration.
- `src/Profile.tsx`, `Roster.tsx`, `AdminAccounts.tsx`, `ModelSettings.tsx`: profile/password controls, scoped roster imports/recycle bins and administrator-only global controls.

## Synthetic browser fixtures — not backend/model evidence

```sh
npm run check:browser
npm run check:stage2
```

Both harnesses exercise real React UI with explicitly intercepted synthetic HTTP responses. They start owned Vite servers on ports **18776** and **18778**, launch the installed Windows Chrome, and close their browser/server in `finally`. No real accounts, model, search service, original materials or learning database are used. Synthetic credentials exist only in the isolated fixtures.

- `tests/artifacts/browser-result.json`: core workflow/layout fixture results and screenshots.
- `artifacts/stage2-fixtures/result.json`: stage2 fixture results, including stored-Chinese-preference rejection, English password/profile UI, durable draft isolation, source removal, dropdown independence, role routing, versions and 390px layouts.
- `artifacts/english-only/unit-tests.xml`, `unit-tests.log`, `build.log`, `verification.json`: English-only unit/build and source/bundle audit evidence.

Successful application mutations read back the relevant backend target before showing success. Fixture checks do not establish real database persistence, backend security isolation, parser quality, model connectivity, deployment or teaching quality; the parent integration lane owns those checks.
