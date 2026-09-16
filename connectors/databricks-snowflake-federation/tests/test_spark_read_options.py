import pytest

from databricks.spark_read_options import build_spark_jdbc_read_options, render_pyspark_snippet
from shared.partitioning import build_partition_plan


def test_requires_exactly_one_of_dbtable_or_query():
    with pytest.raises(ValueError):
        build_spark_jdbc_read_options(host="h", port=1972, namespace="N", user="u", password="p")
    with pytest.raises(ValueError):
        build_spark_jdbc_read_options(
            host="h", port=1972, namespace="N", user="u", password="p",
            dbtable="T", query="SELECT 1",
        )


def test_basic_options_shape():
    opts = build_spark_jdbc_read_options(
        host="iris.example.com", port=1972, namespace="HSFHIR",
        user="u", password="p", dbtable="SQLUser.Patient",
    )
    assert opts["url"] == "jdbc:IRIS://iris.example.com:1972/HSFHIR"
    assert opts["driver"] == "com.intersystems.jdbc.IRISDriver"
    assert opts["dbtable"] == "SQLUser.Patient"
    assert "query" not in opts
    assert opts["fetchsize"] == "10000"


def test_query_form_used_when_dbtable_absent():
    opts = build_spark_jdbc_read_options(
        host="h", port=1972, namespace="N", user="u", password="p",
        query="SELECT id FROM T WHERE x > 1",
    )
    assert opts["query"] == "SELECT id FROM T WHERE x > 1"
    assert "dbtable" not in opts


def test_partition_plan_merges_into_options():
    plan = build_partition_plan(partition_column="id", min_value=1, max_value=1000, row_count=1000)
    opts = build_spark_jdbc_read_options(
        host="h", port=1972, namespace="N", user="u", password="p",
        dbtable="T", partition_plan=plan,
    )
    assert opts["partitionColumn"] == "id"
    assert opts["lowerBound"] == "1"
    assert opts["upperBound"] == "1000"
    assert "numPartitions" in opts


def test_render_pyspark_snippet_redacts_password():
    opts = build_spark_jdbc_read_options(
        host="h", port=1972, namespace="N", user="u", password="topsecret",
        dbtable="T",
    )
    snippet = render_pyspark_snippet(opts)
    assert "topsecret" not in snippet
    assert "***REDACTED***" in snippet
    assert 'spark.read.format("jdbc")' in snippet
