"""Make the ``shared``, ``databricks``, and ``snowflake`` packages in this
directory importable regardless of the working directory pytest is
invoked from.

Note the naming caveat this implies: this directory's local ``snowflake``
and ``databricks`` packages are recipe code, not the real
``snowflake-connector-python`` / Databricks SDKs. Neither of those is
installed in this environment (verified -- see ../STATUS.md), but if this
directory is ever extracted into its own repo (per ../../connectors/README.md)
alongside an environment that *does* have those packages installed, this
directory must not be added to ``sys.path`` / run from as the working
directory of a script that also needs the real packages.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
