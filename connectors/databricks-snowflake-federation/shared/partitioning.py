"""Partitioning-plan math for a Spark JDBC read (``spark.read.format("jdbc")``).

This implements the guidance in the Spark JDBC data source docs and the
Databricks Lakehouse Federation performance-recommendations doc (see
../README.md for the exact citations):

- ``partitionColumn`` must be a numeric, date, or timestamp column.
- ``lowerBound``/``upperBound`` only decide the *stride* of the partitions;
  they do not filter which rows are read back (a common misconception).
  Spark always reads every row in [MIN(partitionColumn), MAX(partitionColumn)]
  once WHERE-filtered; rows outside [lowerBound, upperBound] land in the
  first or last partition rather than being dropped.
- ``numPartitions`` upper-bounds both the parallelism and the number of
  concurrent JDBC connections opened against the source, so it must be
  sized against what the source (here, IRIS) can sustain, not just against
  cluster core count.

None of this touches Spark. It is pure arithmetic so it can be unit tested
without a JVM or a cluster.
"""

from __future__ import annotations

from dataclasses import dataclass


class InvalidPartitionPlan(ValueError):
    pass


@dataclass(frozen=True)
class PartitionPlan:
    partition_column: str
    lower_bound: int
    upper_bound: int
    num_partitions: int
    est_rows_per_partition: float

    def to_spark_options(self) -> dict:
        """The subset of ``spark.read.format("jdbc").options(...)`` keys
        this plan controls. Merge with connection options (url/driver/
        dbtable/user/password) before calling ``.load()``.
        """
        return {
            "partitionColumn": self.partition_column,
            "lowerBound": str(self.lower_bound),
            "upperBound": str(self.upper_bound),
            "numPartitions": str(self.num_partitions),
        }


def build_partition_plan(
    *,
    partition_column: str,
    min_value: int,
    max_value: int,
    row_count: int,
    target_rows_per_partition: int = 500_000,
    max_partitions: int = 64,
    min_partitions: int = 1,
) -> PartitionPlan:
    """Compute a partition plan for a numeric ``partition_column``.

    ``min_value``/``max_value`` should come from ``SELECT MIN(col), MAX(col)
    FROM table`` run against IRIS once, ahead of time -- Spark does not
    compute them for you. ``row_count`` should come from ``SELECT COUNT(*)``.

    Sizing rule: aim for ``target_rows_per_partition`` rows in each of the
    parallel JDBC connections, then clamp to
    ``[min_partitions, max_partitions]`` so a huge table cannot open more
    concurrent connections against IRIS than ``max_partitions`` (protect the
    source), and a tiny table does not get split into pointless partitions.
    """
    if not partition_column:
        raise InvalidPartitionPlan("partition_column must be non-empty")
    if max_value < min_value:
        raise InvalidPartitionPlan(
            f"max_value ({max_value}) must be >= min_value ({min_value})"
        )
    if row_count < 0:
        raise InvalidPartitionPlan("row_count must be >= 0")
    if target_rows_per_partition <= 0:
        raise InvalidPartitionPlan("target_rows_per_partition must be > 0")
    if min_partitions < 1:
        raise InvalidPartitionPlan("min_partitions must be >= 1")
    if max_partitions < min_partitions:
        raise InvalidPartitionPlan("max_partitions must be >= min_partitions")

    if row_count == 0:
        num_partitions = min_partitions
    else:
        ideal = -(-row_count // target_rows_per_partition)  # ceil division
        num_partitions = max(min_partitions, min(max_partitions, ideal))

    # Do not request more partitions than there are distinct values to
    # split across (e.g. a 5-row range should not become 64 partitions).
    value_span = max_value - min_value + 1
    num_partitions = max(1, min(num_partitions, value_span))

    est_rows_per_partition = row_count / num_partitions if num_partitions else float(row_count)

    return PartitionPlan(
        partition_column=partition_column,
        lower_bound=min_value,
        upper_bound=max_value,
        num_partitions=num_partitions,
        est_rows_per_partition=est_rows_per_partition,
    )
