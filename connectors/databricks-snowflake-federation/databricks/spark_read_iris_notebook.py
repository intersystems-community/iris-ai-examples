# Databricks notebook source
# MAGIC %md
# MAGIC # Partitioned Spark JDBC read from InterSystems IRIS
# MAGIC
# MAGIC **Not executed in this environment.** There is no Databricks workspace, no
# MAGIC Spark cluster, and no running IRIS instance available to this task (see
# MAGIC `../STATUS.md`). This notebook is the reproducible recipe; the only things
# MAGIC actually *tested* offline are the pure-Python builders it calls
# MAGIC (`shared/partitioning.py`, `databricks/spark_read_options.py`) -- see
# MAGIC `../tests/`.
# MAGIC
# MAGIC Two ways to get IRIS rows into a Spark DataFrame on Databricks, in order of
# MAGIC recommendation:
# MAGIC
# MAGIC 1. **Plain Spark JDBC** (this notebook) -- works on any cluster with the
# MAGIC    IRIS JDBC driver JAR installed. No Unity Catalog admin setup required.
# MAGIC    Gets Catalyst-level filter pushdown (`PushedFilters`) for free.
# MAGIC 2. **Unity Catalog JDBC connection + foreign catalog** (see `ddl.py` and
# MAGIC    `../README.md`) -- governed, reusable, queryable via
# MAGIC    `catalog.schema.table` syntax from any cluster/SQL warehouse without
# MAGIC    re-entering credentials, but restricted to the connection's
# MAGIC    `externalOptionsAllowList` at query time, and does **not** get
# MAGIC    `remote_query`/aggregate-pushdown (those are documented as available
# MAGIC    only for the named native connectors -- MySQL, PostgreSQL, Oracle,
# MAGIC    Redshift, Snowflake, SQL Server, Teradata, BigQuery -- not for
# MAGIC    bring-your-own JDBC). See ../README.md for the doc citations.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Install the IRIS JDBC driver on the cluster
# MAGIC
# MAGIC Either:
# MAGIC - Attach the driver JAR (`intersystems-jdbc-<version>.jar`) as a
# MAGIC   cluster-scoped library (Compute -> your cluster -> Libraries -> Install
# MAGIC   new -> JAR), or
# MAGIC - Upload it to a Unity Catalog volume and reference it the same way the
# MAGIC   `java_dependencies` option does for a UC JDBC connection (see `ddl.py`).
# MAGIC
# MAGIC The driver ships from InterSystems as part of the IRIS client
# MAGIC redistributables (`intersystems-jdbc` on Maven Central / the InterSystems
# MAGIC download site). Driver class: `com.intersystems.jdbc.IRISDriver`.

# COMMAND ----------

from databricks.spark_read_options import build_spark_jdbc_read_options, render_pyspark_snippet
from shared.partitioning import build_partition_plan

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Look up MIN/MAX/COUNT on IRIS once, ahead of time
# MAGIC
# MAGIC Spark's `lowerBound`/`upperBound` do **not** filter rows -- they only set
# MAGIC partition stride over whatever `partitionColumn` actually contains. Get the
# MAGIC real min/max by running this against IRIS directly (e.g. via
# MAGIC `iris session`, DBeaver, or `python -m iris_pgwire` + psql) before setting
# MAGIC up the read:
# MAGIC
# MAGIC ```sql
# MAGIC SELECT MIN(PatientRowID), MAX(PatientRowID), COUNT(*) FROM SQLUser.Patient
# MAGIC ```
# MAGIC
# MAGIC Pick a `partitionColumn` that is numeric/date/timestamp and, ideally, the
# MAGIC table's clustered index / IDKey -- an unindexed partition column forces a
# MAGIC full scan per partition rather than an indexed range seek, which multiplies
# MAGIC load on IRIS by `numPartitions`.

# COMMAND ----------

# Example values a human would fill in after running the query above.
patient_min_id, patient_max_id, patient_row_count = 1, 4_800_000, 4_800_000

partition_plan = build_partition_plan(
    partition_column="PatientRowID",
    min_value=patient_min_id,
    max_value=patient_max_id,
    row_count=patient_row_count,
    target_rows_per_partition=500_000,
    max_partitions=16,  # cap concurrent JDBC connections IRIS must serve
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Build the read options and load
# MAGIC
# MAGIC `dbtable` here is a parenthesized sub-query, which is how Spark JDBC does
# MAGIC predicate pushdown for *anything beyond* a straight `SELECT *` off a
# MAGIC single table: whatever SQL you put in `dbtable` is what gets sent to IRIS,
# MAGIC once per partition, with the partition's `WHERE PatientRowID BETWEEN ...`
# MAGIC appended by Spark. Column-level filters applied afterwards in the
# MAGIC DataFrame API (`.filter(...)`) get pushed down too and show up as
# MAGIC `PushedFilters` in `.explain()` -- verify this on a real cluster before
# MAGIC relying on it, since pushdown eligibility depends on the JDBC dialect
# MAGIC Spark infers for the driver, and IRIS is not one Spark has a built-in
# MAGIC dialect for (see ../STATUS.md, UNVERIFIED).

# COMMAND ----------

options = build_spark_jdbc_read_options(
    host="iris.example-hospital.internal",
    port=1972,
    namespace="HSFHIR",
    user="spark_reader",
    password=dbutils.secrets.get(scope="iris", key="spark_reader_password"),  # noqa: F821
    dbtable="(SELECT PatientRowID, MRN, BirthDate, SDoHRiskScore FROM SQLUser.Patient) q",
    partition_plan=partition_plan,
    fetchsize=10_000,
)

print(render_pyspark_snippet(options))

# COMMAND ----------

df = spark.read.format("jdbc").options(**options).load()  # noqa: F821

# Column pruning + filter pushdown: only ask for what you need, and filter
# on the partition column or another indexed column where possible.
high_risk = df.select("MRN", "SDoHRiskScore").filter("SDoHRiskScore >= 7")
high_risk.explain(True)  # confirm PushedFilters includes SDoHRiskScore >= 7

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. The Unity Catalog connection alternative
# MAGIC
# MAGIC For a governed, reusable connection instead of embedding credentials in a
# MAGIC notebook, run the DDL `databricks/ddl.py` generates once (as a workspace
# MAGIC admin), then read via:
# MAGIC
# MAGIC ```python
# MAGIC df = spark.read.table("iris_federation.HSFHIR.Patient")
# MAGIC ```
# MAGIC
# MAGIC or, in SQL:
# MAGIC
# MAGIC ```sql
# MAGIC SELECT MRN, SDoHRiskScore FROM iris_federation.HSFHIR.Patient WHERE SDoHRiskScore >= 7;
# MAGIC ```
# MAGIC
# MAGIC Partitioning options (`partitionColumn`/`lowerBound`/`upperBound`/
# MAGIC `numPartitions`) still apply, but must be passed as query-time Spark
# MAGIC options, which only works if they are present in the connection's
# MAGIC `externalOptionsAllowList` (the Databricks-documented default already
# MAGIC includes all four -- see `ddl.py`).
