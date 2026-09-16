"""Generate parameterised Azure Data Factory ARM JSON for InterSystems IRIS,
via the generic ODBC linked service, from a small connection config and a
table list.

This is the testable core described in ../README.md: instead of a human
retyping the same Odbc linked service / dataset / copy-activity JSON for
every table and environment (and getting it subtly wrong -- inlining a
password, forgetting connectVia, mistyping the connection string), this
module builds it programmatically from data.

Nothing here calls Azure. It only builds Python dicts that serialize to the
JSON documents ARM (or `az datafactory linked-service create --properties
...`) expects. See ../README.md for why ODBC (not JDBC) is the connector
this module targets, and ../STATUS.md for what has and has not been
verified against a live factory.
"""
from __future__ import annotations

from dataclasses import dataclass, field

API_VERSION = "2018-06-01"
FACTORY_RESOURCE_TYPE = "Microsoft.DataFactory/factories"

# Characters that force an ODBC keyword value to be wrapped in {..braces..}
# per the InterSystems / generic ODBC connection-string grammar (a value
# containing the delimiter ';', the assignment '=', or a brace must be
# quoted, and any literal '}' inside a braced value is doubled). This is the
# same quoting rule documented for the Windows/unixODBC driver managers the
# InterSystems ODBC driver plugs into.
_NEEDS_BRACES = set(";={}")


def _odbc_quote(value: str) -> str:
    if not value:
        return value
    if any(ch in _NEEDS_BRACES for ch in value):
        return "{" + value.replace("}", "}}") + "}"
    return value


@dataclass
class IrisConnectionConfig:
    """Everything needed to build an ODBC connection string and linked
    service for one IRIS instance, minus the password (which never lives in
    this object -- see key_vault_secret_name)."""

    host: str
    username: str
    key_vault_secret_name: str
    port: int = 1972
    namespace: str = "USER"
    # Driver name as it will be registered in odbcinst.ini on the
    # self-hosted IR machine. This varies across IRIS versions/platforms
    # ("InterSystems ODBC35", "InterSystems ODBC", "InterSystems IRIS
    # ODBC35 x64" on some Windows installs) -- see README "Verifying the
    # driver name on your self-hosted IR host". There is no single global
    # constant that is correct for every install, so it is a required,
    # explicit parameter rather than a hardcoded default.
    driver_name: str = "InterSystems ODBC35"
    extra_odbc_params: dict = field(default_factory=dict)
    key_vault_linked_service_name: str = "AzureKeyVaultLinkedService"
    key_vault_secret_version: str | None = None

    def __post_init__(self) -> None:
        if not (0 < self.port < 65536):
            raise ValueError(f"port out of range: {self.port}")
        if not self.host:
            raise ValueError("host is required")
        if not self.username:
            raise ValueError("username is required")
        if not self.key_vault_secret_name:
            raise ValueError(
                "key_vault_secret_name is required -- the password is never "
                "accepted directly by this generator"
            )


def build_connection_string(config: IrisConnectionConfig) -> str:
    """Build the ODBC connection string for the *non-secret* portion only.

    Deliberately excludes PWD. ADF's Odbc linked service keeps the secret
    portion in a separate `password` (or `credential`) field so it can be a
    Key Vault reference instead of plaintext; folding PWD into this string
    would defeat that and is exactly the mistake this generator exists to
    prevent. See tests/test_secrets.py.
    """
    parts = [
        f"Driver={{{config.driver_name}}}",
        f"Server={_odbc_quote(config.host)}",
        f"Port={config.port}",
        f"Database={_odbc_quote(config.namespace)}",
        f"UID={_odbc_quote(config.username)}",
    ]
    for key, value in sorted(config.extra_odbc_params.items()):
        parts.append(f"{key}={_odbc_quote(str(value))}")
    return ";".join(parts) + ";"


def _split_odbc_segments(connection_string: str) -> list[str]:
    """Split on ';' but not inside a {braced} value (a braced value may
    itself contain ';' or '=', which is exactly why build_connection_string
    braces such values instead of leaving them to corrupt the split)."""
    segments = []
    current = []
    depth = 0
    for ch in connection_string:
        if ch == "{":
            depth += 1
            current.append(ch)
        elif ch == "}":
            depth = max(0, depth - 1)
            current.append(ch)
        elif ch == ";" and depth == 0:
            segments.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        segments.append("".join(current))
    return segments


def parse_connection_string(connection_string: str) -> dict:
    """Inverse of build_connection_string, for round-trip testing. Not used
    at runtime by ADF -- this is a test/debugging helper."""
    result: dict[str, str] = {}
    for segment in _split_odbc_segments(connection_string):
        segment = segment.strip()
        if not segment or "=" not in segment:
            continue
        key, _, value = segment.partition("=")
        if value.startswith("{") and value.endswith("}"):
            value = value[1:-1].replace("}}", "}")
        result[key] = value
    return result


def _factory_resource(
    resource_subtype: str,
    factory_name: str,
    name: str,
    properties: dict,
    depends_on: list[str] | None = None,
) -> dict:
    """Build one Microsoft.DataFactory/factories/<resource_subtype> ARM
    resource, meant to be nested inside a parent 'factories' resource (see
    wrap_arm_template). Per the real ARM schema
    (resourceDefinitions.factories_linkedservices.properties.name), a
    literal (non-expression) resource `name` may NOT contain '/' -- so the
    factory name is carried by nesting, not by concatenating it into this
    resource's own name. An earlier version of this generator produced
    "factoryName/childName" as a flat top-level resource name, which fails
    that pattern; tests/test_schema_validation.py pins this down.
    """
    resource = {
        "type": f"{FACTORY_RESOURCE_TYPE}/{resource_subtype}",
        "apiVersion": API_VERSION,
        "name": name,
        "properties": properties,
    }
    if depends_on:
        resource["dependsOn"] = depends_on
    # factory_name isn't used in `name` itself (see above) but every caller
    # threads it through so resourceId()-based dependsOn expressions and any
    # future per-factory scoping stay consistent.
    _ = factory_name
    return resource


def build_self_hosted_ir(factory_name: str, ir_name: str = "IrisSelfHostedIR") -> dict:
    """The self-hosted integration runtime resource. IRIS/Caché has no
    Azure IR path (see README) -- the SHIR always has to exist first, with
    the InterSystems ODBC driver installed on that same host."""
    return _factory_resource(
        "integrationRuntimes",
        factory_name,
        ir_name,
        {"type": "SelfHosted", "description": "Self-hosted IR with the InterSystems ODBC driver installed."},
    )


def build_keyvault_linked_service(
    factory_name: str,
    key_vault_base_url: str,
    name: str = "AzureKeyVaultLinkedService",
) -> dict:
    return _factory_resource(
        "linkedservices",
        factory_name,
        name,
        {"type": "AzureKeyVault", "typeProperties": {"baseUrl": key_vault_base_url}},
    )


def build_iris_linked_service(
    config: IrisConnectionConfig,
    factory_name: str,
    name: str = "IrisOdbcLinkedService",
    integration_runtime_name: str = "IrisSelfHostedIR",
) -> dict:
    properties = {
        "type": "Odbc",
        "typeProperties": {
            "connectionString": build_connection_string(config),
            "authenticationType": "Basic",
            "userName": config.username,
            "password": {
                "type": "AzureKeyVaultSecret",
                "store": {
                    "referenceName": config.key_vault_linked_service_name,
                    "type": "LinkedServiceReference",
                },
                "secretName": config.key_vault_secret_name,
                **(
                    {"secretVersion": config.key_vault_secret_version}
                    if config.key_vault_secret_version
                    else {}
                ),
            },
        },
        "connectVia": {
            "referenceName": integration_runtime_name,
            "type": "IntegrationRuntimeReference",
        },
    }
    return _factory_resource(
        "linkedservices",
        factory_name,
        name,
        properties,
        depends_on=[
            f"[resourceId('Microsoft.DataFactory/factories/integrationRuntimes', "
            f"'{factory_name}', '{integration_runtime_name}')]"
        ],
    )


def build_blob_linked_service(
    factory_name: str,
    key_vault_linked_service_name: str,
    storage_connection_string_secret_name: str,
    name: str = "SinkBlobLinkedService",
) -> dict:
    """Sink linked service for the Azure Storage side of the copy. The
    storage connection string is also a Key Vault reference -- same policy
    as the IRIS password, not an exception for the "easy" side."""
    return _factory_resource(
        "linkedservices",
        factory_name,
        name,
        {
            "type": "AzureBlobStorage",
            "typeProperties": {
                "connectionString": {
                    "type": "AzureKeyVaultSecret",
                    "store": {
                        "referenceName": key_vault_linked_service_name,
                        "type": "LinkedServiceReference",
                    },
                    "secretName": storage_connection_string_secret_name,
                },
                "accountKind": "StorageV2",
            },
        },
    )


def _sanitize_name(table_name: str) -> str:
    """ADF resource names may not contain '.', so 'SQLUser.Patient' becomes
    'SQLUser_Patient'."""
    return table_name.replace(".", "_").replace(" ", "_")


def build_iris_dataset(
    factory_name: str,
    table_name: str,
    linked_service_name: str = "IrisOdbcLinkedService",
    dataset_name: str | None = None,
) -> dict:
    dataset_name = dataset_name or f"IrisTable_{_sanitize_name(table_name)}"
    return _factory_resource(
        "datasets",
        factory_name,
        dataset_name,
        {
            "type": "OdbcTable",
            "linkedServiceName": {
                "referenceName": linked_service_name,
                "type": "LinkedServiceReference",
            },
            "typeProperties": {"tableName": table_name},
        },
        depends_on=[
            f"[resourceId('Microsoft.DataFactory/factories/linkedservices', "
            f"'{factory_name}', '{linked_service_name}')]"
        ],
    )


def build_blob_dataset(
    factory_name: str,
    table_name: str,
    container: str,
    linked_service_name: str = "SinkBlobLinkedService",
    dataset_name: str | None = None,
    folder_path: str | None = None,
) -> dict:
    dataset_name = dataset_name or f"BlobSink_{_sanitize_name(table_name)}"
    location = {"type": "AzureBlobStorageLocation", "container": container}
    if folder_path:
        location["folderPath"] = folder_path
    location["fileName"] = f"{_sanitize_name(table_name)}.csv"
    return _factory_resource(
        "datasets",
        factory_name,
        dataset_name,
        {
            "type": "DelimitedText",
            "linkedServiceName": {
                "referenceName": linked_service_name,
                "type": "LinkedServiceReference",
            },
            "typeProperties": {
                "location": location,
                "columnDelimiter": ",",
                "firstRowAsHeader": True,
            },
        },
        depends_on=[
            f"[resourceId('Microsoft.DataFactory/factories/linkedservices', "
            f"'{factory_name}', '{linked_service_name}')]"
        ],
    )


def build_copy_pipeline(
    factory_name: str,
    table_name: str,
    source_dataset_name: str,
    sink_dataset_name: str,
    pipeline_name: str | None = None,
    query: str | None = None,
) -> dict:
    pipeline_name = pipeline_name or f"CopyIris_{_sanitize_name(table_name)}"
    query = query or f"SELECT * FROM {table_name}"
    activity = {
        "name": f"Copy_{_sanitize_name(table_name)}",
        "type": "Copy",
        "inputs": [{"referenceName": source_dataset_name, "type": "DatasetReference"}],
        "outputs": [{"referenceName": sink_dataset_name, "type": "DatasetReference"}],
        "typeProperties": {
            "source": {"type": "OdbcSource", "query": query},
            "sink": {"type": "DelimitedTextSink"},
        },
        "policy": {"retry": 1, "retryIntervalInSeconds": 30, "timeout": "0.00:30:00"},
    }
    return _factory_resource(
        "pipelines",
        factory_name,
        pipeline_name,
        {"activities": [activity]},
        depends_on=[
            f"[resourceId('Microsoft.DataFactory/factories/datasets', "
            f"'{factory_name}', '{source_dataset_name}')]",
            f"[resourceId('Microsoft.DataFactory/factories/datasets', "
            f"'{factory_name}', '{sink_dataset_name}')]",
        ],
    )


def wrap_arm_template(
    resources: list[dict],
    factory_name: str,
    location: str = "eastus2",
    parameters: dict | None = None,
) -> dict:
    """Nest the given child resources under a Microsoft.DataFactory/factories
    resource. Nesting (rather than a flat top-level list with
    "factoryName/childName" resource names) is what lets each child's
    literal `name` satisfy the real ARM schema's no-slash pattern -- see
    _factory_resource's docstring.
    """
    factory_resource = {
        "type": FACTORY_RESOURCE_TYPE,
        "apiVersion": API_VERSION,
        "name": factory_name,
        "location": location,
        "resources": resources,
    }
    return {
        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
        "contentVersion": "1.0.0.0",
        "parameters": parameters or {},
        "resources": [factory_resource],
    }


def generate_bundle(
    config: IrisConnectionConfig,
    tables: list[str],
    factory_name: str,
    key_vault_base_url: str,
    storage_container: str,
    storage_connection_string_secret_name: str,
) -> dict:
    """Build the full set of ARM resources for copying `tables` out of one
    IRIS instance into Azure Blob Storage, and return them both as a single
    combined ARM template and as the individual resource dicts (the latter
    is what the tests exercise directly).

    Returns
    -------
    dict with keys:
      "template": one ARM template containing every resource below
      "self_hosted_ir", "keyvault_linked_service", "iris_linked_service",
      "blob_linked_service": single resource dicts
      "datasets": {table_name: {"source": ..., "sink": ...}}
      "pipelines": {table_name: pipeline_dict}
    """
    if not tables:
        raise ValueError("tables must be a non-empty list")

    sanitized = [_sanitize_name(t) for t in tables]
    seen: dict[str, str] = {}
    for table, clean in zip(tables, sanitized):
        if clean in seen and seen[clean] != table:
            raise ValueError(
                "table names collide after sanitizing for ADF resource "
                f"names (both '.' and '_' map to '_'): {seen[clean]!r} and "
                f"{table!r} both become {clean!r}. Pass distinct "
                "dataset_name/pipeline_name overrides via the lower-level "
                "build_iris_dataset/build_copy_pipeline functions instead "
                "of generate_bundle for this table set."
            )
        seen[clean] = table

    kv_ls_name = config.key_vault_linked_service_name

    shir = build_self_hosted_ir(factory_name)
    kv_ls = build_keyvault_linked_service(factory_name, key_vault_base_url, name=kv_ls_name)
    iris_ls = build_iris_linked_service(config, factory_name)
    blob_ls = build_blob_linked_service(
        factory_name,
        kv_ls_name,
        storage_connection_string_secret_name,
    )

    datasets: dict[str, dict] = {}
    pipelines: dict[str, dict] = {}
    resources = [shir, kv_ls, iris_ls, blob_ls]

    for table in tables:
        source_ds = build_iris_dataset(factory_name, table)
        sink_ds = build_blob_dataset(factory_name, table, storage_container)
        pipeline = build_copy_pipeline(
            factory_name,
            table,
            source_dataset_name=source_ds["name"],
            sink_dataset_name=sink_ds["name"],
        )
        datasets[table] = {"source": source_ds, "sink": sink_ds}
        pipelines[table] = pipeline
        resources.extend([source_ds, sink_ds, pipeline])

    return {
        "template": wrap_arm_template(resources, factory_name=factory_name),
        "self_hosted_ir": shir,
        "keyvault_linked_service": kv_ls,
        "iris_linked_service": iris_ls,
        "blob_linked_service": blob_ls,
        "datasets": datasets,
        "pipelines": pipelines,
    }
