"""Build the option dict for a partitioned ``spark.read.format("jdbc")``
read from IRIS, and the two ways to run it on Databricks:

1. Direct Spark JDBC (no Unity Catalog connection object) -- the fallback
   path any Databricks cluster with the IRIS JDBC driver JAR installed can
   use today, with no admin setup beyond installing the driver.
2. Through a Unity Catalog JDBC connection + foreign catalog (see ddl.py) --
   governed, reusable across clusters, but option pass-through at query
   time is restricted to the connection's ``externalOptionsAllowList``.

Both still run on core Spark's JDBC data source, so both get the same
Catalyst-level filter pushdown (``PushedFilters`` in the physical plan) for
a ``spark.read.format("jdbc")`` load -- that pushdown is a property of
Spark's JDBC relation provider, not of Lakehouse Federation's SQL-engine
pushdown (which is a separate, source-specific mechanism documented per
connector and NOT available for bring-your-own JDBC connections; see
../README.md).

This module only builds the options dict. It does not import pyspark and
is fully unit-testable without a cluster.
"""

from __future__ import annotations

from shared.iris_jdbc import IRIS_JDBC_DRIVER_CLASS, build_jdbc_url
from shared.partitioning import PartitionPlan


def build_spark_jdbc_read_options(
    *,
    host: str,
    port: int,
    namespace: str,
    user: str,
    password: str,
    dbtable: str | None = None,
    query: str | None = None,
    partition_plan: PartitionPlan | None = None,
    fetchsize: int = 10_000,
) -> dict:
    """Build the full options dict for
    ``spark.read.format("jdbc").options(**opts).load()``.

    Exactly one of ``dbtable`` or ``query`` must be given, matching Spark's
    own JDBC data source contract (``dbtable`` for a full/filtered table
    push, ``query`` for an arbitrary source-side SQL query -- Spark forbids
    supplying both).

    ``fetchsize`` controls how many rows the IRIS JDBC driver buffers per
    network round trip; the Spark JDBC docs note the JDBC default is
    usually small (row-at-a-time) and recommend raising it for bulk reads.
    """
    if bool(dbtable) == bool(query):
        raise ValueError("exactly one of dbtable or query must be provided")

    options: dict = {
        "url": build_jdbc_url(host, port, namespace),
        "driver": IRIS_JDBC_DRIVER_CLASS,
        "user": user,
        "password": password,
        "fetchsize": str(fetchsize),
    }
    if dbtable:
        options["dbtable"] = dbtable
    else:
        options["query"] = query

    if partition_plan is not None:
        options.update(partition_plan.to_spark_options())

    return options


def render_pyspark_snippet(options: dict) -> str:
    """Render the options dict as the ``.option(...)`` chain a notebook
    cell would use, for copy-paste into ``spark_read_iris_notebook.py``.
    Password is rendered as a placeholder, never as the real value, since
    this text is meant to be pasted into a notebook cell / committed to
    source control.
    """
    lines = ["df = (", "    spark.read.format(\"jdbc\")"]
    for key, value in options.items():
        rendered = "***REDACTED***" if key == "password" else value
        lines.append(f"    .option(\"{key}\", \"{rendered}\")")
    lines.append("    .load()")
    lines.append(")")
    return "\n".join(lines)
