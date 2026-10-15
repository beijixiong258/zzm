"""Task-local Codex budget gate. Called by real work, not a resident service."""
from pathlib import Path
from datetime import datetime, timezone
import json
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts/ocr-stage1'
OUT.mkdir(parents=True, exist_ok=True)
STOP = OUT / 'STOP'
STATUS = OUT / 'budget-status.json'
QUERY = Path('C:/Users/17193/AppData/Local/hermes/skills/hermes/hermes-usage-query/scripts/query_usage.py')
PYTHON = Path('C:/Users/17193/.hermes/projects/hermes-panel/.venv/Scripts/python.exe')


def check(force=False):
    if STOP.exists():
        raise SystemExit('PAUSED: ' + STOP.read_text(encoding='utf-8'))
    if not force and STATUS.exists():
        old = json.loads(STATUS.read_text(encoding='utf-8'))
        if time.time() - old.get('checked_epoch', 0) < 120:
            return old
    last = None
    for _ in range(2):
        try:
            p = subprocess.run([str(PYTHON), str(QUERY), '--json'], capture_output=True, text=True, encoding='utf-8', timeout=75)
            if p.returncode:
                raise RuntimeError('usage query failed')
            data = json.loads(p.stdout)
            rate = data.get('rate_limit', {})
            windows = rate.get('windows') or [rate.get(k) for k in ('primary_window', 'secondary_window') if rate.get(k)]
            if data.get('proxy_error') or not windows:
                raise RuntimeError('usage windows unavailable')
            sanitized = [{'label': w.get('label', w.get('slot', 'window')), 'used_percent': float(w['used_percent']), 'remaining_percent': 100 - float(w['used_percent']), 'reset_at': w.get('reset_at_text')} for w in windows]
            result = {'checked_epoch': time.time(), 'checked_at': datetime.now(timezone.utc).isoformat(), 'windows': sanitized, 'remaining_min_percent': min(w['remaining_percent'] for w in sanitized)}
            result['paused'] = result['remaining_min_percent'] < 1 or bool(rate.get('limit_reached'))
            temp = STATUS.with_suffix('.tmp.' + str(__import__('os').getpid()))
            temp.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
            temp.replace(STATUS)
            with (OUT / 'budget-log.jsonl').open('a', encoding='utf-8') as f:
                f.write(json.dumps(result) + '\n')
            if result['paused']:
                STOP.write_text('Quota remaining below 1%; save progress and wait for user.\n', encoding='utf-8')
                raise SystemExit('PAUSED: quota below user threshold')
            return result
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            last = type(exc).__name__
    STOP.write_text('Quota could not be verified after two attempts (' + str(last) + '); checkpoint before further model work.\n', encoding='utf-8')
    raise SystemExit('PAUSED: quota unavailable')


if __name__ == '__main__':
    print(json.dumps(check(force=True), indent=2))
