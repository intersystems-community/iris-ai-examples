import pytest

from shared.partitioning import InvalidPartitionPlan, build_partition_plan


def test_basic_partition_plan_sizes_by_target_rows_per_partition():
    plan = build_partition_plan(
        partition_column="PatientRowID",
        min_value=1,
        max_value=4_800_000,
        row_count=4_800_000,
        target_rows_per_partition=500_000,
        max_partitions=64,
    )
    assert plan.partition_column == "PatientRowID"
    assert plan.lower_bound == 1
    assert plan.upper_bound == 4_800_000
    # ceil(4_800_000 / 500_000) == 10
    assert plan.num_partitions == 10
    assert plan.est_rows_per_partition == pytest.approx(480_000)


def test_partition_plan_caps_at_max_partitions():
    plan = build_partition_plan(
        partition_column="id",
        min_value=1,
        max_value=100_000_000,
        row_count=100_000_000,
        target_rows_per_partition=1_000,  # would want 100_000 partitions
        max_partitions=64,
    )
    assert plan.num_partitions == 64


def test_partition_plan_respects_min_partitions_floor():
    plan = build_partition_plan(
        partition_column="id",
        min_value=1,
        max_value=100,
        row_count=10,
        target_rows_per_partition=500_000,
        min_partitions=2,
        max_partitions=64,
    )
    assert plan.num_partitions >= 2


def test_partition_plan_does_not_exceed_value_span():
    # Only 5 distinct values in range -- must not ask for more partitions
    # than that, even if row_count/target math would suggest more.
    plan = build_partition_plan(
        partition_column="small_enum",
        min_value=1,
        max_value=5,
        row_count=10_000_000,
        target_rows_per_partition=1,
        max_partitions=64,
    )
    assert plan.num_partitions <= 5


def test_partition_plan_zero_rows_uses_min_partitions():
    plan = build_partition_plan(
        partition_column="id",
        min_value=1,
        max_value=10,
        row_count=0,
        min_partitions=1,
    )
    assert plan.num_partitions == 1


def test_partition_plan_rejects_max_less_than_min():
    with pytest.raises(InvalidPartitionPlan):
        build_partition_plan(partition_column="id", min_value=100, max_value=1, row_count=10)


def test_partition_plan_rejects_negative_row_count():
    with pytest.raises(InvalidPartitionPlan):
        build_partition_plan(partition_column="id", min_value=1, max_value=10, row_count=-5)


def test_partition_plan_rejects_empty_partition_column():
    with pytest.raises(InvalidPartitionPlan):
        build_partition_plan(partition_column="", min_value=1, max_value=10, row_count=10)


def test_partition_plan_rejects_max_partitions_below_min_partitions():
    with pytest.raises(InvalidPartitionPlan):
        build_partition_plan(
            partition_column="id",
            min_value=1,
            max_value=10,
            row_count=10,
            min_partitions=5,
            max_partitions=2,
        )


def test_to_spark_options_shape():
    plan = build_partition_plan(partition_column="id", min_value=1, max_value=100, row_count=100)
    opts = plan.to_spark_options()
    assert opts == {
        "partitionColumn": "id",
        "lowerBound": str(plan.lower_bound),
        "upperBound": str(plan.upper_bound),
        "numPartitions": str(plan.num_partitions),
    }
    # Spark JDBC options are strings, not ints -- catches a common bug.
    assert all(isinstance(v, str) for v in opts.values())
