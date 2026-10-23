"""CPU-only command line; consumes saved responses, never starts a model/service."""
from __future__ import annotations
import argparse
import html
import json
from pathlib import Path
import re
import shutil

from tools.document_stage12.parser_helpers import dump, sha256
from .adapter import CropPolicy, verify_readback, write_image_bundle
from .prepared import augment_prepared_bundle
from .provenance import resolve_experiment_trace


def application_validation(root):
    from backend.aicademiya.document_bundle import Manifest, validate_bundle
    from pydantic import ValidationError
    root = Path(root)
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    try:
        Manifest.model_validate(manifest)
        validate_bundle(root, manifest['source_sha256'], manifest['page_count'])
        return {'valid': True}
    except ValidationError as error:
        details = [{'location': list(e['loc']), 'type': e['type']} for e in error.errors(include_input=False)]
        return {'valid': False, 'status': 'pending_parent_optional_field_integration',
                'errors': details, 'unknown_fields': sorted({str(e['loc'][-1]) for e in error.errors() if e['type'] == 'extra_forbidden'})}
    except ValueError as error:
        return {'valid': False, 'status': 'application_validation_failed', 'error': str(error)}


def _has_markdown_table(text):
    return bool(re.search(r'^\s*\|?\s*:?-{3,}:?\s*\|', text, re.MULTILINE))


def consume_experiment(experiment, app_root, output):
    experiment, app, out = Path(experiment), Path(app_root), Path(output)
    saved = json.loads((experiment / 'output/result.json').read_text(encoding='utf-8'))
    declared = json.loads((experiment / 'inputs.json').read_text(encoding='utf-8'))
    reviewed = json.loads((experiment / 'review-summary.json').read_text(encoding='utf-8'))
    cases = saved['cases']
    names = [c['name'] for c in cases]
    if len(set(names)) != len(names) or sorted(names) != sorted(declared) or reviewed['returned'] != len(cases) or reviewed['requested'] != len(declared):
        raise ValueError('Experiment enumeration differs from declared/reviewed totals')
    out.mkdir(parents=True, exist_ok=False)
    for name in ('source-manifest.json', 'inputs.json', 'review-summary.json'):
        target = out / 'raw' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(experiment / name, target)
    shutil.copyfile(experiment / 'output/result.json', out / 'raw/result.json')
    rows = []
    for case in sorted(cases, key=lambda c: c['name']):
        name = case['name']
        if Path(name).name != name or not re.fullmatch(r'[A-Za-z0-9_-]+\.png', name):
            raise ValueError('Experiment image name must be a simple PNG name')
        raster = experiment / 'input' / name
        digest = sha256(raster)
        if digest != case['sha256']:
            raise ValueError('Actual input SHA differs from saved model case: ' + name)
        response_file = experiment / 'output' / (Path(name).stem + '-response.json')
        response = json.loads(response_file.read_text(encoding='utf-8'))
        choice = response['choices'][0]
        if choice['message']['content'] != case['content'] or choice['finish_reason'] != case['finish_reason']:
            raise ValueError('Saved response does not match result case')
        mapping = resolve_experiment_trace(app, experiment, name, digest)
        destination = out / 'bundles' / Path(name).stem
        receipt = write_image_bundle(raster, response, destination,
            expected_raster_sha256=digest, source_mapping=mapping, response_file=response_file)
        manifest = json.loads((destination / 'manifest.json').read_text(encoding='utf-8'))
        protocol = json.loads(case['content'])
        row = {'name': name, 'bundle': destination.relative_to(out).as_posix(),
            'source_sha256': digest, 'source_trace': mapping,
            'finish_reason': case['finish_reason'], 'model_calls': 0,
            'input_candidates': len(protocol['images']), 'body_characters': len(protocol['body_text']),
            'body_text_format': 'markdown', 'model_markdown_table_present': _has_markdown_table(protocol['body_text']),
            'blocks': len(manifest['pages'][0]['blocks']),
            'needs_review_blocks': receipt['validation']['needs_review_blocks'],
            'source_image_assets': receipt['readback']['source_image_assets'],
            'parser_validation': receipt['validation'], 'readback': receipt['readback'],
            'application_validation': application_validation(destination)}
        rows.append(row)
        # Persist each completed case before continuing, retaining actual progress.
        with (out / 'case-results.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    rows = [json.loads(line) for line in (out / 'case-results.jsonl').read_text(encoding='utf-8').splitlines()]
    if len(rows) != len(declared) or len({r['name'] for r in rows}) != len(declared):
        raise ValueError('Persisted consumption count mismatch')
    candidate_total = sum(r['input_candidates'] for r in rows)
    if candidate_total != reviewed['visual_regions']:
        raise ValueError('Actual candidate total differs from review-summary assertion')
    summary = {'status': 'complete_local_adapter_evidence', 'expected': len(declared), 'consumed': len(rows),
        'parser_valid_bundles': sum(r['parser_validation']['valid'] for r in rows),
        'readback_valid_bundles': sum(r['readback']['valid'] for r in rows),
        'application_valid_bundles': sum(r['application_validation']['valid'] for r in rows),
        'input_candidates': candidate_total, 'source_image_assets': sum(r['source_image_assets'] for r in rows),
        'whole_source_assets': sum(r['readback']['whole_sources'] for r in rows),
        'source_region_assets': sum(sum(e['role'] == 'candidate_region' for e in r['readback']['evidence']) for r in rows),
        'blocks': sum(r['blocks'] for r in rows), 'body_characters': sum(r['body_characters'] for r in rows),
        'needs_review_blocks': sum(r['needs_review_blocks'] for r in rows),
        'recorded_source_page_traces': sum(r['source_trace']['kind'] == 'recorded_source_page' for r in rows),
        'standalone_only_traces': sum(r['source_trace']['kind'] == 'standalone_image_source' for r in rows),
        'model_markdown_table_cases': sum(r['model_markdown_table_present'] for r in rows),
        'markdown_table_real_model_acceptance': False, 'semantic_accuracy_approved': False,
        'independent_verification': False, 'model_calls': 0,
        'source_hashes': {r['name']: r['source_sha256'] for r in rows},
        'cases': [{k: r[k] for k in ('name', 'bundle', 'blocks', 'body_characters', 'input_candidates',
                    'source_image_assets', 'application_validation')} for r in rows]}
    dump(out / 'summary.json', summary)
    dump(out / 'source-hashes.json', {'result_sha256': sha256(experiment / 'output/result.json'),
          'source_manifest_sha256': sha256(experiment / 'source-manifest.json'),
          'rasters': summary['source_hashes'],
          'originals': {r['source_trace']['source_id']: r['source_trace']['source_sha256'] for r in rows if r['source_trace'].get('original_hash_checked')}})
    cards = []
    for row in rows:
        base = row['bundle']
        cards.append('<section><h2>' + html.escape(row['name']) + '</h2><p>Source PNG SHA: <code>' + row['source_sha256'] + '</code></p>'
            + '<a href="' + base + '/manifest.json">schema1 manifest</a> · '
            + '<a href="' + base + '/raw/p0001-adapter.json">raw mapping / candidates / uncertainty</a> · '
            + '<a href="' + base + '/preview.pdf">derived preview</a>'
            + '<img alt="Retained complete source raster" src="' + base + '/pages/p0001.png">'
            + ''.join('<figure><img alt="Source pixel crop" src="' + base + '/' + e['asset']
                + '"><figcaption>' + html.escape(e['block_id'] + ' ' + str(e['pixel_bbox'])) + '</figcaption></figure>'
                for e in row['readback']['evidence'] if e['role'] == 'candidate_region') + '</section>')
    (out / 'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Stage15 local adapter evidence</title>'
        + '<style>body{max-width:1100px;margin:24px auto;font:16px sans-serif}img{max-width:100%}figure{display:inline-block;width:45%;vertical-align:top}code{overflow-wrap:anywhere}section{border-top:1px solid #ccc;padding:20px 0}</style>'
        + '<h1>Stage15 · local source-pixel evidence</h1><p>Imported real responses, zero new model calls. Descriptions/transcriptions remain unverified. Markdown table preservation is tested separately using protocol fixtures.</p>'
        + ''.join(cards), encoding='utf-8')
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    single = sub.add_parser('image')
    single.add_argument('--input', required=True)
    single.add_argument('--response', required=True)
    single.add_argument('--sha256', required=True)
    single.add_argument('--output', required=True)
    single.add_argument('--source-mapping')
    single.add_argument('--body-format', choices=('plain', 'markdown'), default='markdown')
    batch = sub.add_parser('consume')
    batch.add_argument('--experiment', required=True)
    batch.add_argument('--app-root', default=str(Path(__file__).resolve().parents[2]))
    batch.add_argument('--output', required=True)
    read = sub.add_parser('verify')
    read.add_argument('--bundle', required=True)
    prepared = sub.add_parser('prepared')
    prepared.add_argument('--input', required=True)
    prepared.add_argument('--pages', required=True, help='JSON list of page_inputs')
    prepared.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    if args.command == 'consume':
        result = consume_experiment(args.experiment, args.app_root, args.output)
        print(json.dumps({k: v for k, v in result.items() if k not in ('cases', 'source_hashes')}, ensure_ascii=False, indent=2))
    elif args.command == 'verify':
        result = verify_readback(args.bundle)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == 'prepared':
        result = augment_prepared_bundle(args.input, args.output, json.loads(Path(args.pages).read_text(encoding='utf-8')))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        response_path = Path(args.response)
        mapping = json.loads(Path(args.source_mapping).read_text(encoding='utf-8')) if args.source_mapping else None
        result = write_image_bundle(args.input, json.loads(response_path.read_text(encoding='utf-8')), args.output,
            expected_raster_sha256=args.sha256, response_file=response_path,
            source_mapping=mapping, body_format=args.body_format)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
