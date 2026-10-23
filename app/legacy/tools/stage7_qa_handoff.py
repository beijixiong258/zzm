"""Write Stage7 QA handoff from exact selected JSON evidence; never rerun or edit app.
Refuses to overwrite the handoff. Individual runs/DBs/logs are retained unchanged.
"""
import argparse
import hashlib
import json
from pathlib import Path

from stage7_qa_helpers import ROOT, write_json


def load(path):
    path = Path(path).resolve()
    return path, json.loads(path.read_text(encoding='utf-8'))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--strict-result', required=True)
    p.add_argument('--prefinal-result', required=True)
    p.add_argument('--settings-result', required=True)
    a = p.parse_args()
    strict_path, strict = load(a.strict_result)
    pre_path, pre = load(a.prefinal_result)
    settings_path, settings = load(a.settings_result)
    target = ROOT / 'artifacts/stage7/qa-handoff'
    if (target / 'HANDOFF.md').exists() or (target / 'coverage.json').exists():
        raise RuntimeError('Existing handoff must be reviewed/updated deliberately; run history is never overwritten')
    strict_groups = {g['name']: g for g in strict['groups']}
    pre_groups = {g['name']: g for g in pre['groups']}
    api, production, browser = strict_groups['api'], strict_groups['production-demo-http-gate'], pre_groups['browser']
    assert all(g['status'] == 'passed' for g in (api, production, browser))
    assert not strict['final_acceptance'] and not pre['final_acceptance']
    assert pre['frontend_build']['explicit_allow_stale_build'] and browser['acceptance']['final_evidence'] is False
    selected = [('Current-source real HTTP API', strict_path, api),
                ('Normal-runtime demo-disabled HTTP gate', strict_path, production),
                ('Explicit pre-final Stage6-labelled browser', pre_path, browser)]
    records = []
    for label, handle, g in selected:
        acc = g['acceptance']
        assert len(acc['checks']) == len(set(acc['checks'])), 'Duplicated declared check names'
        assert not acc['failures']
        assert g['owned_server_stopped'] and g['owned_listener_closed']
        assert g['sqlite']['integrity_check'] == 'ok' and g['sqlite']['schema_version'] == 5 and not g['sqlite']['foreign_key_check']
        if g['name'] == 'browser':
            assert acc['cleanup']['owned_browser_closed'] and acc['cleanup']['owned_debug_listener_closed']
        records.append({'label': label, 'run_result': str(handle), 'group': g['name'], 'check_count': len(acc['checks']),
                        'request_count': acc['request_count'], 'checks': acc['checks'], 'screenshots': acc.get('screenshots', []),
                        'cleanup': {'owned_server_stopped': True, 'owned_listener_closed': True, 'browser': acc.get('cleanup')},
                        'sqlite': {k: g['sqlite'][k] for k in ('integrity_check', 'schema_version', 'foreign_key_check')},
                        'protocol_metrics': g['no_model_guard']})
    previous_settings_count = sum(len(g.get('browser', {}).get('checks', [])) for g in settings['groups'])
    history = []
    for path in sorted(target.glob('run-*/result.json')):
        _, s = load(path)
        history.append({'handle': str(path), 'status': s['status'], 'final_acceptance': s['final_acceptance'],
                        'groups': [{'name': g['name'], 'status': g['status'], 'checks': len(g.get('acceptance', {}).get('checks', [])), 'failures': g.get('acceptance', {}).get('failures', []), 'reason': g.get('reason')} for g in s['groups']]})
    names = ['run_stage7_integration.py', 'stage7_api_acceptance.py', 'stage7_browser_acceptance.mjs', 'stage7_qa_helpers.py', 'stage7_browser_qa_helpers.mjs', 'stage7_qa_handoff.py']
    coverage = {'final_acceptance': False, 'selected_verified_groups': records,
                'historical_settings': {'handle': str(settings_path), 'status': settings['status'], 'browser_check_count': previous_settings_count, 'current_merged_state_verified': False},
                'unverified': ['Final natural teacher labels and four task tabs', 'Sources & instructions/preview technical Details collapsed by default', 'Advanced/timing keyboard expansion in new teacher layout', 'New CourseLibrary actual row membership/linked-session navigation and mobile layout', 'Final merged student/material/teacher layout after UI child merges', 'Current merged parent Settings browser/API/process restart composition', 'Full backend/frontend/package suites, release/Linux/backup/production preservation/deployment', 'Real model teaching quality and real Tavily results'],
                'run_history': history, 'tool_source_sha256': {name: hashlib.sha256((ROOT / 'tools' / name).read_bytes()).hexdigest() for name in names},
                'visual_review': {'stage7-mobile-help.png': 'Observed real390px tooltip inside viewport, legible, no horizontal clipping.', 'stage7-student-mobile-workspace.png': 'Observed reachable composer and Web search Off; top conversation position is scrolled, not a missing-record claim.', 'desktop-stale-preview.png': 'Observed explicit stale warning and readable old transcript in old Stage6 layout. Not final Stage7 visual acceptance.'},
                'evidence_boundary': 'Generated synthetic catalogs and uploads only. Real app HTTP/native extraction/SQLite. No app-route interception, real inference/search or production18773 access. Provider transport fixtures and demo delay/fail-once are labelled. First workspace GET initializes an operational row; no-write opening starts after initialization.'}
    write_json(target / 'coverage.json', coverage)
    lines = ['# Stage7 merged acceptance QA handoff', '',
             '**Partial, not final acceptance.** Tooling is authored and executed; current-source API/SQLite and an explicitly stale Stage6-labelled browser lane are verified. The strict final browser guard correctly blocks the current parent-owned dist. No app code, shared/Stage6/parent Settings tools, frontend/dist, sample_data, or production data were modified.', '',
             '## Verified evidence', '', '| Group | Passed checks | HTTP observations | Result handle |', '|---|---:|---:|---|']
    for r in records:
        lines.append(f'| {r["label"]} | {r["check_count"]} | {r["request_count"]} | `{Path(r["run_result"]).relative_to(ROOT).as_posix()}` → `{r["group"]}/result.json` |')
    lines += ['', f'- Browser screenshots: **{len(browser["acceptance"]["screenshots"])}**, retained under `{pre_path.parent.relative_to(ROOT).as_posix()}/browser/`.',
              '- All selected local DBs: integrity `ok`, schema5, FK violations0. Owned servers/listeners stopped; browser/CDP listener closed. Exact table counts/memberships, safe preview records and message modes: each group `runner.json`.',
              '- Model/search actual-call counters are0. Explicit bounded provider transport probes are fixtures only; probe payload boundaries and demo delay/fail-once entries: `no-model-metrics.json`. No actual model/search result is claimed.',
              f'- Historical parent Settings group: {previous_settings_count} browser/API checks plus real process restart/SQLite evidence at `{settings_path.relative_to(ROOT).as_posix()}`. Attached as historical, **not counted as current merged acceptance**.',
              '- All exact check names, evidence paths, protocol counts, visual review notes, source hashes and retained failed attempts are in `coverage.json`.', '',
              '### Checked responsibilities',
              '- Complete Stage6 API scenario imported by version-only AST rebase0.5.0→0.6.0; source/compiler/import native extraction, read-only all-table equality, duplicate-ID/budget/private gates, save→stale→reset/oldID409, immutable student/history/version, full-preview query-token save/submit/reference/reading preserved.',
              '- Added canonical CourseLibrary API two-session/unassigned memberships, same-ID attach/idempotence, cross-course and ownership403/422 gates, private downloads/preview, key visibility and referenced-detach409, shared metadata, historical authorized downloads, immutable versions and restoration.',
              '- Added actual concurrent pending/reset409 and accepted-failure raw-input preservation; unchanged retry ID and completed replay do not duplicate saved messages/revisions. Classification is intentionally not fabricated before successful feedback.',
              '- Added Settings role GET/PUT/test gates, safe frozen DTO/no-secret projections, independent save/readback, no automatic probes, connection timestamps/failure/invalidation/stale409, explicit clear/blank/disabled search and demo-not-connectivity semantics.',
              '- Added demo-disabled create_app HTTP gate: legacy saved/environment demo cannot enable normal runtime, demo auth403 and admin demo save422; unconfigured tutor502 and no deterministic fallback messages.',
              '- Pre-final browser exercised all retained workbench import/source/save/pending/retry/stale/reset/old-tab/full-preview submit-reference/process-facts/raw-navigation/mobile checks, plus Settings role shell, Active AI Model, keyboard/tap help, real brand/dirty Settings and teaching/raw-hash protection, mobile student saved response/version identity/web-search-off.', '',
              '## Parent final gate (not checked here)',
              '- Merge both Phase C UI lanes, then parent rebuilds frontend/dist. This harness never builds or waits/polls child artifacts.',
              '- Run the strict merged browser, including natural four task labels, collapsed Sources & instructions/preview technical details/Advanced, real CourseLibrary row membership and linked-session/mobile navigation. New checks are implemented, deliberately excluded only by explicit legacy pre-final flag.',
              '- Recompose the parent-owned Settings15-check browser/API/SQLite/restart group against the final build. Current final run is not replaced by the earlier15-check proof.',
              '- Full backend/frontend/package/release/isolated-Linux/backup/production preservation/deployment remain parent-owned; no real-model quality claim.', '',
              '## Commands', '', 'From `D:/HermesProjects/EDUC7703/app`:', '', '```bash',
              '# Final: requires parent-built current dist and all merged labels/components',
              './.venv/Scripts/python.exe tools/run_stage7_integration.py --compose-settings', '',
              '# Independent real API + normal-runtime gate now; explicitly not final',
              './.venv/Scripts/python.exe tools/run_stage7_integration.py --skip-browser', '',
              '# Explicit PRE-FINAL existing dist only; never reports final_acceptance=true',
              './.venv/Scripts/python.exe tools/run_stage7_integration.py --allow-stale-build --pre-final-legacy-labels', '',
              '# Future external isolated Linux QA; confirmation required, NEVER production18773',
              './.venv/Scripts/python.exe tools/run_stage7_integration.py --base-url http://ISOLATED_QA_HOST:QA_PORT --confirm-test-data --chrome-path /path/to/chrome',
              '```', '',
              '- Defaults create a NEW `artifacts/stage7/qa-handoff/run-*`. Existing run folder reuse is refused. Partial with blocked browser returns exit1; explicit skip/pre-final partial lanes can return0, but JSON `final_acceptance` remainsfalse. Final pass requires strict current/source-dist-stable state, API+browser+normal-runtime+Settings composition.',
              '- External mode cannot inspect remote SQLite/processes or provide local fault fixtures; those missing assertions are labelled boundaries. Operator must independently provide schema/FK/cleanup/no-model and normal-runtime evidence. Final composition is local-only because parent Settings runner is Windows/local-owned.', '',
              '## Presentation coupling points for final merge',
              '- `stage7_browser_acceptance.mjs` final labels require `Tutor preview`, `Save draft`, `Import instructions`; explicit `--pre-final-legacy-labels` is the ONLY old-label lane.',
              '- `stage7_browser_qa_helpers.mjs`: final teacher `Teaching session sections` nav must expose exactly the four contractual task entries; native `details > summary` selectors use `Sources & instructions`, preview `Details|Technical`, and `Advanced|Timing|Schedule`. If children intentionally use another accessible label, update only presentation selectors, not semantic assertions.',
              '- CourseLibrary UI helper currently expects the canonical row in `article|tr|li`, both real session titles in that row, and a linked-session button named with `Synthetic library destination`. Parent should reconcile this selector to the merged CourseLibrary source while preserving exact membership/readback/nav proof.',
              '- Existing structural selectors `.tf-additional`, `.tw-source-result`, `.guided-reference`, `.process-totals`, raw `data-message-id`, `Browse questions` and revision navigation are retained from Stage6. Source budget count/capacity UTF-8 labels remain strict; do not remove identity/budget assertions for a text change.',
              '- Browser retains compact preview `Test response`, reset/confirmation, full-preview `Progress & responses`, teacher process-facts and raw-record navigation controls; if presentation changed, repair locators without replacing real HTTP/SQLite readbacks with mocked routes.', '',
              '## Failed history (retained; harness fixes only)',
              '- First API fixture read a Tavily credential from JSON instead of its actual Authorization header; corrected to actual protocol shape. No app fix.',
              '- First pending-failure assertion wrongly expected an answer classification before successful feedback. Real DB showed accepted raw user message with prior attempt intact; corrected to preserve raw input/no invented classified answer, then retry/idempotence assertions.',
              '- First stale-browser attempt had an indemo Active AI label expectation, shell authentication writes placed inside no-write baseline, and a checkbox selector for the actual Web search switch. Corrected harness setup/ordering/role selectors; the replacement pre-final browser25-check lane passed.', '',
              '## New files', *[f'- `tools/{name}`' for name in names], '- This folder `HANDOFF.md`, `coverage.json`, all retained `run-*` catalogs/fixtures/results/logs/SQLite/screenshots. No shared tools or app edits.']
    (target / 'HANDOFF.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'handoff': str(target / 'HANDOFF.md'), 'groups': [{'label': r['label'], 'checks': r['check_count'], 'requests': r['request_count']} for r in records], 'screenshots': len(browser['acceptance']['screenshots']), 'historical_settings_checks': previous_settings_count, 'retained_runs': len(history)}))


if __name__ == '__main__':
    main()
