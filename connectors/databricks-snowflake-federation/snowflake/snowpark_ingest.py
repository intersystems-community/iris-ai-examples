"""Recommended Snowflake-side recipe: pull rows from IRIS into Snowflake
with Snowpark Python, through an External Access Integration.

**Not executed in this environment.** There is no Snowflake account and no
running IRIS instance available to this task (see ../STATUS.md). This
module is the reproducible recipe plus the pure-Python DDL/config builders
it calls (`snowflake/ddl.py`, `shared/iris_jdbc.py`) -- those are what
../tests/ actually exercises.

Two ways to reach IRIS from inside a Snowpark Python function, in order of
recommendation:

1. **DB-API via iris-pgwire + psycopg2 (recommended, GA)**. Snowpark
   Python's DB-API integration is GA and documented as working with any
   DBAPI 2.0-compliant Python driver (Snowflake's own examples use
   psycopg2, oracledb, pymssql). `psycopg2`/`psycopg` is exactly such a
   driver, and `intersystems-community/iris-pgwire` puts a real PostgreSQL
   wire-protocol front end in front of IRIS -- so this is "connect to IRIS
   as if it were Postgres" using a Snowflake feature that is already GA,
   with no JAR upload and no preview-feature risk. See README.md for why
   this is the recommended path and for the residual, unverified risk
   (pgwire's catalog emulation is partial -- see ../STATUS.md).

2. **JDBC via Snowpark's JDBC API (fallback, public preview)**. Upload the
   InterSystems JDBC driver JAR to a Snowflake stage and use Snowpark's
   JDBC reader directly against IRIS. No pgwire dependency, but the
   feature itself is public preview, not GA, as of this research (see
   README.md citation).
"""

from __future__ import annotations

from shared.iris_jdbc import IRIS_JDBC_DRIVER_CLASS, build_pgwire_dsn
from snowflake.ddl import ExternalAccessSpec, build_all_ddl


def render_setup_ddl(
    *,
    host: str,
    pgwire_port: int,
    user: str,
    password: str,
    network_rule_name: str = "iris_pgwire_network_rule",
    secret_name: str = "iris_pgwire_secret",
    integration_name: str = "iris_pgwire_access_integration",
) -> str:
    """Render the three CREATE statements a Snowflake ACCOUNTADMIN/
    appropriately-privileged role runs once, before any Snowpark function
    can reach IRIS.
    """
    spec = ExternalAccessSpec(
        network_rule_name=network_rule_name,
        secret_name=secret_name,
        integration_name=integration_name,
        host=host,
        port=pgwire_port,
        user=user,
        password=password,
    )
    return "\n\n".join(build_all_ddl(spec))


def render_snowpark_dbapi_function(
    *,
    host: str,
    pgwire_port: int,
    namespace: str,
    user: str,
    integration_name: str = "iris_pgwire_access_integration",
    secret_name: str = "iris_pgwire_secret",
    dbtable: str = "SQLUser.Patient",
) -> str:
    """Render the Python UDTF/stored-procedure body a human pastes into a
    Snowflake worksheet or `snowsql`. Uses Snowpark's GA Python DB-API
    integration (`session.read.dbapi`) with psycopg2 talking to IRIS
    through iris-pgwire. Password is pulled from the Snowflake SECRET at
    call time via `_snowflake.get_generic_secret_string`, never embedded.
    """
    dsn_template = build_pgwire_dsn(host, pgwire_port, namespace, user, password="{password}")
    return f'''# Snowflake stored procedure / notebook cell.
# Requires: EXTERNAL ACCESS INTEGRATIONS = ({integration_name})
# Requires: PACKAGES = ('snowflake-snowpark-python', 'psycopg2')

import _snowflake
import psycopg2


def read_iris_table(session, dbtable: str = "{dbtable}"):
    password = _snowflake.get_generic_secret_string("{secret_name}")
    dsn = "{dsn_template}".format(password=password)

    def make_conn():
        return psycopg2.connect(dsn)

    # session.read.dbapi is Snowpark Python's GA DB-API reader: it accepts
    # any DBAPI 2.0 connection factory and pulls rows into a Snowpark
    # DataFrame, executing in parallel across the warehouse.
    df = session.read.dbapi(make_conn, table=dbtable)
    df.write.save_as_table("IRIS_{dbtable.split(".")[-1].upper()}", mode="overwrite")
    return f"loaded {{df.count()}} rows from {{dbtable}}"
'''


def render_snowpark_jdbc_function(
    *,
    host: str,
    port: int,
    namespace: str,
    integration_name: str = "iris_jdbc_access_integration",
    secret_name: str = "iris_jdbc_secret",
    driver_jar_stage_path: str = "@iris_drivers/intersystems-jdbc.jar",
    dbtable: str = "SQLUser.Patient",
) -> str:
    """Render the fallback path: Snowpark's public-preview JDBC API,
    talking to IRIS's own JDBC driver directly (no pgwire dependency).
    """
    return f'''# Snowflake stored procedure / notebook cell. Public-preview API.
# Requires: EXTERNAL ACCESS INTEGRATIONS = ({integration_name})
# Requires: PACKAGES = ('snowflake-snowpark-python')
# Requires: the JDBC driver JAR staged at {driver_jar_stage_path}

import _snowflake


def read_iris_table_jdbc(session, dbtable: str = "{dbtable}"):
    password = _snowflake.get_generic_secret_string("{secret_name}")
    df = session.read.jdbc(
        url="jdbc:IRIS://{host}:{port}/{namespace}",
        driver="{IRIS_JDBC_DRIVER_CLASS}",
        driver_jar="{driver_jar_stage_path}",
        dbtable=dbtable,
        properties={{"user": "spark_reader", "password": password}},
    )
    df.write.save_as_table("IRIS_{dbtable.split(".")[-1].upper()}", mode="overwrite")
    return f"loaded {{df.count()}} rows from {{dbtable}}"
'''
