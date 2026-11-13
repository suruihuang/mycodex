"""Paths and engine settings from config.toml at the repository root.

Copy config.example.toml to config.toml and edit it, or point MUTMECH_CONFIG at another file.
Relative paths are taken from the repository root.
"""
import os
import tomllib

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PATH = os.environ.get('MUTMECH_CONFIG') or os.path.join(REPO, 'config.toml')
if not os.path.exists(_PATH):
    raise SystemExit(f'no config at {_PATH}: copy config.example.toml to config.toml and set the paths')
with open(_PATH, 'rb') as f:
    _CFG = tomllib.load(f)


def _abs(p):
    return p if os.path.isabs(p) else os.path.join(REPO, p)


P = _CFG['paths']
INPUT_CSV = _abs(P['input_csv'])
WORKBOOK = _abs(P['curator_workbook'])
TESTSET = _abs(P['testset_dir'])
NUMBERING_MAP = _abs(P['numbering_map'])
STRUCTURE_DIRS = [_abs(d) for d in P['structure_dirs']]
SKEMPI_CSV = _abs(P['skempi_csv'])
RUNS = _abs(P['runs_dir'])
FORBIDDEN = [_abs(d) for d in P.get('forbidden_dirs', [])]
DEV_LLM_RUN = _abs(P['dev_llm_run']) if P.get('dev_llm_run') else ''
SKILLS = {'v3': _abs(P.get('skills_v3', '')), 'v4': _abs(P.get('skills_v4') or os.path.join(REPO, 'skills', 'v4')),
          'stmt': os.path.join(REPO, 'skills', 'stmt')}
CODEX = os.environ.get('CODEX') or _abs(_CFG['engine']['codex'])
MODEL = os.environ.get('CODEX_MODEL', _CFG['engine'].get('model', ''))
BASELINE_SKILL = os.path.join(REPO, 'skills', 'baseline', 'SKILL.md')
PROMPTS = os.path.join(REPO, 'prompts')
# first-500 benchmark: answers, inputs and the finished runs that `score` and `reproduce` read; all optional
FIRST500 = {k: _abs(v) for k, v in _CFG.get('first500', {}).items() if v}
