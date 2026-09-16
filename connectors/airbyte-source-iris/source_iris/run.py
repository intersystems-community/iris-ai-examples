#
# source-iris: CLI entrypoint. Mirrors the pattern used by every Python-CDK connector
# in airbytehq/airbyte (e.g. source-firebolt's source_firebolt/run.py).
#

import sys

from airbyte_cdk.entrypoint import launch

from .source import IrisSource


def run() -> None:
    source = IrisSource()
    launch(source, sys.argv[1:])


if __name__ == "__main__":
    run()
