"""Shared, dependency-free helpers for the Databricks and Snowflake IRIS
federation recipes.

Nothing in this package talks to a network. It only builds strings (JDBC
URLs, DSNs, SQL DDL fragments) and validates them against the documented
grammar of the target system. See ../README.md for citations.
"""
