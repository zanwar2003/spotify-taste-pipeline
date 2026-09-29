"""python -m tastepipe.silver [--max-reject-rate 0.5]"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict

import psycopg

from .load import DEFAULT_MAX_REJECT_RATE, QualityGateError, build_silver


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the silver layer from bronze.")
    parser.add_argument(
        "--max-reject-rate",
        type=float,
        default=DEFAULT_MAX_REJECT_RATE,
        help="abort without writing if more than this fraction of records fail validation",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("tastepipe.silver")
    url = os.environ.get("DATABASE_URL")
    if not url:
        log.error("DATABASE_URL is not set")
        return 1

    with psycopg.connect(url) as conn:
        try:
            summary = build_silver(conn, args.max_reject_rate)
        except QualityGateError as exc:
            log.error("quality gate failed: %s", exc)
            return 2
    log.info("silver build complete: %s", json.dumps(asdict(summary)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
