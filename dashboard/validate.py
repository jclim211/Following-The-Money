"""Run the BQ1 dashboard data checks from the command line.

Usage:  python validate.py            (reads ./data_bq1)
        python validate.py path/to/folder

Prints PASS/FAIL for every check in handoff section 18 and exits with code 1
if any check fails. Save the output as validation evidence.
"""
import sys
from datetime import datetime
from pathlib import Path

import bq1_data as bd


def main() -> int:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "data_bq1"
    print(f"BQ1 dashboard data checks · {datetime.now():%Y-%m-%d %H:%M} · folder: {data_dir}")
    try:
        queue = bd.load_queue(data_dir / bd.QUEUE_FILE)
        capacity = bd.load_capacity(data_dir / bd.CAPACITY_FILE)
    except FileNotFoundError as err:
        print(f"FAIL  could not find file: {err.filename}")
        return 1
    except bd.SchemaError as err:
        print(f"FAIL  schema problem: {err}")
        return 1

    checks = bd.run_checks(queue, capacity)
    for c in checks:
        print(f"{'PASS' if c.passed else 'FAIL'}  {c.name:<55} {c.detail}")
    failed = sum(not c.passed for c in checks)
    print(f"\n{len(checks) - failed}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
