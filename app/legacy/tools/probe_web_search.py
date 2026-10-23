"""Verify Tavily directly, without invoking any LLM. Output contains no key."""
from pathlib import Path
from datetime import datetime
import argparse
import json
import os
import re
import shlex
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.aicademiya.web_search import TavilySearch, SearchFailure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--key-env-file', type=Path, help='Read only TAVILY_API_KEY from this dotenv file; never source it as shell code')
    parser.add_argument('--save-local-config', action='store_true', help='Save the authorized Tavily key and search switch into ignored local-settings.json; preserve AI mode')
    parser.add_argument('--query', default='site.cambridgeenglish.org language assessment validity reliability')
    args = parser.parse_args()
    if args.key_env_file:
        for line in args.key_env_file.read_text(encoding='utf-8-sig').splitlines():
            match = re.match(r'^\s*(?:export\s+)?TAVILY_API_KEY\s*=\s*(.*)$', line)
            if match:
                pieces = shlex.split(match[1], comments=True)
                if len(pieces) == 1:
                    os.environ['TAVILY_API_KEY'] = pieces[0]
                break
    elif not os.getenv('TAVILY_API_KEY'):
        config = json.loads((ROOT/'local-settings.json').read_text(encoding='utf-8-sig'))
        os.environ['TAVILY_API_KEY'] = config.get('TAVILY_API_KEY', '')
    start = time.monotonic()
    try:
        result = TavilySearch().search(args.query)
    except SearchFailure as exc:
        print(str(exc))
        return 1
    result.update(status='passed' if result['results'] else 'empty_results', provider='tavily',
                  seconds=round(time.monotonic()-start, 2), verified_at=datetime.now().astimezone().isoformat(),
                  real_search=True, real_model=False, model_requests=0)
    if args.save_local_config:
        path = ROOT/'local-settings.json'
        current = json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else {}
        mode_before = current.get('AICADEMIYA_AI_MODE')
        current.update(AICADEMIYA_WEB_SEARCH_ENABLED='true', TAVILY_API_KEY=os.environ['TAVILY_API_KEY'])
        path.write_text(json.dumps(current, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        saved = json.loads(path.read_text(encoding='utf-8'))
        assert saved['TAVILY_API_KEY'] == os.environ['TAVILY_API_KEY'] and saved.get('AICADEMIYA_AI_MODE') == mode_before
        result['local_config_saved'] = True
        result['ai_mode_unchanged'] = mode_before
    output = ROOT/'artifacts/web-search'
    output.mkdir(parents=True, exist_ok=True)
    (output/'tavily-live.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='results'}, ensure_ascii=False, indent=2))
    print(json.dumps({'results_count':len(result['results']), 'sources':[{'title':r['title'],'url':r['url']} for r in result['results']]}, ensure_ascii=False, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
