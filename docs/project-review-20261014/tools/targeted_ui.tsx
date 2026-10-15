// Exercise current components with synthetic material/profile inputs.
import React from '../../../app/frontend/node_modules/react/index.js';
import { renderToStaticMarkup } from '../../../app/frontend/node_modules/react-dom/server.node.js';
import Materials from '../../../app/frontend/src/Materials';
import { defaultTeachingProfile, teachingProfileErrors, teachingPreviewKey } from '../../../app/frontend/src/teaching-profile';
import fs from 'node:fs';

const formats = ['pptx', 'docx', 'doc', 'txt', 'md', 'png', 'jpg', 'jpeg', 'webp', 'ppt', 'xls', 'xlsx'];
const results = formats.map(source_format => {
  const material = { id: 'review-' + source_format, title: 'Synthetic source ' + source_format, kind: 'reference', visibility: 'student', source_label: 'Synthetic review', status: 'processing', excerpt: '', source_format, processing: 'full_document', preview_kind: 'text' };
  const markup = renderToStaticMarkup(<Materials materials={[material as any]} teacher />);
  return { source_format, no_document_yet: true, non_pdf_preview: true, processing_status_entry: markup.includes('Complete document / processing status') };
});
const profile = { ...defaultTeachingProfile(), tone: '😀'.repeat(600) };
const session = { id: 'review-session', title: 'Original', instructions: '', learning_objectives: [], teaching_language: 'en', reference_policy: 'after_attempt', teaching_profile: defaultTeachingProfile(), questions: [], reference_answers: {} };
const changed = { ...session, title: 'Changed', questions: [{ id: 'review-q', prompt: 'Changed prompt' }], reference_answers: { 'review-q': 'Changed key' } };
const result = {
  material_format_entries: results,
  utf16_limit_case: { codepoints: Array.from(profile.tone).length, utf16_units: profile.tone.length, current_errors: teachingProfileErrors(profile) },
  teaching_readback_key_case: { different_title_questions_references: true, current_key_equal: teachingPreviewKey(session as any) === teachingPreviewKey(changed as any) },
  method: 'Actual React static rendering and current pure helper functions with synthetic inputs',
  network_calls: 0,
};
fs.writeFileSync('D:/HermesProjects/EDUC7703/docs/project-review-20261014/evidence/targeted-ui-observations.json', JSON.stringify(result, null, 2));
console.log(JSON.stringify(result, null, 2));
