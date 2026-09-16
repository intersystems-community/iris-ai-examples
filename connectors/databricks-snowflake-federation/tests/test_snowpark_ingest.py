from snowflake.snowpark_ingest import (
    render_setup_ddl,
    render_snowpark_dbapi_function,
    render_snowpark_jdbc_function,
)


def test_render_setup_ddl_contains_all_three_statements_in_order():
    ddl = render_setup_ddl(host="iris.example.com", pgwire_port=5432, user="_SYSTEM", password="SYS")
    assert ddl.index("CREATE OR REPLACE NETWORK RULE") < ddl.index("CREATE OR REPLACE SECRET")
    assert ddl.index("CREATE OR REPLACE SECRET") < ddl.index("CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION")
    assert "iris.example.com:5432" in ddl


def test_render_snowpark_dbapi_function_never_embeds_real_password():
    code = render_snowpark_dbapi_function(
        host="iris.example.com", pgwire_port=5432, namespace="HSFHIR", user="_SYSTEM",
    )
    assert "get_generic_secret_string" in code
    assert "session.read.dbapi" in code
    assert "psycopg2" in code
    # DSN template uses a {password} placeholder, filled at call time from
    # the Snowflake secret -- never a literal password baked into the code.
    assert "{password}" in code


def test_render_snowpark_jdbc_function_uses_iris_driver_class():
    code = render_snowpark_jdbc_function(host="iris.example.com", port=1972, namespace="HSFHIR")
    assert "com.intersystems.jdbc.IRISDriver" in code
    assert "jdbc:IRIS://iris.example.com:1972/HSFHIR" in code
    assert "get_generic_secret_string" in code
