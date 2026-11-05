"""Export the explicit nominal-geometry example with Python standard library."""

import argparse
import json
import sys
from pathlib import Path

from .court import nominal_court, render_svg


def main():
    if len(sys.argv) == 1 or sys.argv[1] == 'monitor':
        from .monitor import main as monitor_main
        return monitor_main(sys.argv[2:] if len(sys.argv) > 1 else [])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True,
                        help='A NEW directory; existing paths are never overwritten.')
    args = parser.parse_args()
    try:
        args.output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error('Output already exists; choose a new directory.')
    court = nominal_court()
    (args.output / 'court.json').write_text(
        json.dumps(court, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (args.output / 'court.svg').write_text(render_svg(court), encoding='utf-8')
    print('Exported nominal geometry only; NOT camera calibration or real tracking.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
