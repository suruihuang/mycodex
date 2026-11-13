"""mutmech: one entry point for the MutMech tools.

  python -m mutmech analyze ...     one mutation or a small batch, from a quote or a PDF, with a chosen rule
  python -m mutmech pipeline ...    batch runs of the LLM methods (run, compare)
  python -m mutmech routing ...     routing v0 (ids, score)
  python -m mutmech routing-v1 ...  routing v1 (score)
  python -m mutmech skempi-join     join the input records to SKEMPI 2.0
  python -m mutmech score ...       score a finished run on the first-500 benchmark
  python -m mutmech reproduce       check the logged numbers, no LLM calls
  python -m mutmech serve           local web GUI on 127.0.0.1 (analyze, batch, history)
Each command takes --help.
"""
import sys


def main():
    from importlib import import_module
    commands = {'analyze': 'analyze', 'pipeline': 'pipeline', 'routing': 'routing', 'routing-v1': 'routing_v1',
                'skempi-join': 'skempi', 'score': 'score', 'reproduce': 'reproduce', 'serve': 'serve'}
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        print(__doc__)
        sys.exit(0 if len(sys.argv) > 1 and sys.argv[1] in ('-h', '--help') else 2)
    cmd = sys.argv[1]
    sys.argv = [f'mutmech {cmd}'] + sys.argv[2:]
    import_module(f'mutmech.{commands[cmd]}').main()
