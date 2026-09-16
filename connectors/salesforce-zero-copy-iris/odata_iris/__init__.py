"""odata_iris — a minimal OData v4 producer over InterSystems IRIS SQL tables.

Scope and labeling (read this before using any of this code):

This package implements *Salesforce Connect external objects* / generic
OData v4 query-federation semantics over IRIS. It does **not** implement,
and does not grant access to, the Salesforce "Zero Copy Partner Network"
(the branded, co-marketed program whose GA members are AWS/Redshift,
Databricks, Google BigQuery, Snowflake and Microsoft Fabric). See
../README.md and ../STATUS.md for the full distinction and citations.

What this package actually gives a caller:
  - a $metadata (CSDL/EDMX) document generated from a declared table schema
  - translation of $filter / $select / $top / $skip / $orderby into a
    parameterized SQL SELECT statement, safe against injection
  - no network layer, no IRIS connection: SQL generation is decoupled from
    execution behind a small DB-API-shaped Protocol so tests run with a
    fake connection and no Docker/IRIS is required.
"""
