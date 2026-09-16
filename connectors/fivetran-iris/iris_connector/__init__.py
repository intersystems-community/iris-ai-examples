"""IRIS source connector for the Fivetran Connector SDK.

This package holds everything that is *not* the Fivetran entrypoint itself
(`connector.py` at the project root). Splitting it out this way means the
production code can be exercised by plain `pytest` against a fake DB-API
connection, with no dependency on the `fivetran_connector_sdk` runtime, the
`iris` driver, or a live IRIS instance.
"""
