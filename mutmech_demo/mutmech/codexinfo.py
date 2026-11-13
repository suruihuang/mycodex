"""What Codex actually ran with, read from its own session record.

`codex exec --json` prints a thread id first; Codex keeps a rollout file for that thread under
$CODEX_HOME/sessions (default ~/.codex/sessions) whose turn_context names the model and settings.
"""
import glob
import json
import os

CODEX_HOME = os.environ.get('CODEX_HOME', os.path.expanduser('~/.codex'))


def thread_id(events_path):
    try:
        with open(events_path, encoding='utf-8') as f:
            for line in f:
                e = json.loads(line)
                if e.get('type') == 'thread.started':
                    return e.get('thread_id')
    except (OSError, ValueError):
        return None
    return None


def session_info(events_path):
    """Model, provider, effort, sandbox and approval policy of the call that wrote events_path."""
    tid = thread_id(events_path)
    info = {'thread_id': tid, 'rollout': None, 'model': None, 'reasoning_effort': None, 'model_provider': None,
            'cli_version': None, 'approval_policy': None, 'sandbox': None, 'network_access': None}
    if not tid:
        return info
    hits = glob.glob(os.path.join(CODEX_HOME, 'sessions', '**', f'rollout-*{tid}.jsonl'), recursive=True)
    if not hits:
        return info
    info['rollout'] = hits[0]
    with open(hits[0], encoding='utf-8') as f:
        for line in f:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            p = o.get('payload') or {}
            if o.get('type') == 'session_meta':
                info['model_provider'] = p.get('model_provider')
                info['cli_version'] = p.get('cli_version')
            elif o.get('type') == 'turn_context':
                info['model'] = p.get('model')
                info['reasoning_effort'] = ((p.get('collaboration_mode') or {}).get('settings') or {}).get('reasoning_effort')
                info['approval_policy'] = p.get('approval_policy')
                sp = p.get('sandbox_policy') or {}
                info['sandbox'] = sp.get('type')
                info['network_access'] = sp.get('network_access')
                break
    return info


def token_usage(events_path):
    total = {}
    try:
        with open(events_path, encoding='utf-8') as f:
            for line in f:
                e = json.loads(line)
                if e.get('type') == 'turn.completed' and isinstance(e.get('usage'), dict):
                    for k, v in e['usage'].items():
                        if isinstance(v, int):
                            total[k] = total.get(k, 0) + v
    except (OSError, ValueError):
        pass
    return total


def observed_models(run_dir):
    models = set()
    for f in glob.glob(os.path.join(run_dir, '**', '*.session.json'), recursive=True):
        try:
            m = json.load(open(f, encoding='utf-8')).get('model')
        except (OSError, ValueError):
            continue
        if m:
            models.add(m)
    return sorted(models)
