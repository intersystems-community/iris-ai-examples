"""
iris_tool_bridge — expose Python iris_llm ToolSets through the IRIS MCP Server.

Usage (from embedded Python / ##class(%SYS.Python)):

    import sys
    sys.path.insert(0, "/path/to/aicore/python/embedded")
    from iris_tool_bridge import register_toolset

    from iris_llm import ToolSet, tool

    class MyTools(ToolSet):
        @tool
        def search_patients(self, mrn: str, name: str = "") -> str:
            \"\"\"Search for patients by MRN or name.\"\"\"
            import iris
            rows = list(iris.sql.exec(
                "SELECT TOP 5 ID, Name FROM HS.FHIR.DTL.vSTU3.Model.Resource.Patient "
                "WHERE MRN = ? OR Name %STARTSWITH ?",
                [mrn, name]
            ))
            return str(rows)

    cls_name = register_toolset(MyTools, namespace="AICOREAPPLICATION")
    # cls_name is e.g. "Tmp.Bridge.MyTools" — use it in any agent or MCP service

How it works:
    1. Reads the ToolSet's catalog (JSON schema from @tool decorators).
    2. Code-generates an ObjectScript %AI.Tool subclass where each method:
       a. Reconstructs the Python ToolSet instance via ##class(%SYS.Python).
       b. Calls the @tool method with the arguments passed by the dispatcher.
       c. Returns the result as a %DynamicObject.
    3. Compiles the generated class into IRIS via %Compiler.
    4. Also generates and compiles a thin %AI.ToolSet wrapper that includes it.
    5. Returns the ToolSet class name for immediate use.

Limitations:
    - Only works from embedded Python (sys._embedded=1, i.e. ##class(%SYS.Python)).
    - Generated classes live in the Tmp.Bridge.* package — they are transient
      and not persisted across IRIS restarts unless you export and import the .cls.
    - Complex return types are JSON-serialised to string.
    - No support for streaming tools or async tools.
"""

from __future__ import annotations

import contextlib
import inspect
import json
import os
import sys
import textwrap
from typing import Any, Type

from iris_llm import ToolSet


@contextlib.contextmanager
def iris_stdout():
    """No-op context manager — kept for API compatibility.

    Previously attempted fd-level redirection around LoadStream, but IRIS
    tracks fd 1 internally and os.dup2 after LoadStream corrupts its state,
    causing SIGSEGV on the next IRIS→Python dispatch.  The LoadStream compile
    messages ("Load started / Load finished") go directly through IRIS's C
    layer and cannot be safely suppressed from Python without patching IRIS.

    Leave compile messages as-is; they go to the terminal and are informative.
    """
    yield


# ---------------------------------------------------------------------------
# Module-level registry: toolset classes registered for ObjectScript dispatch
# ---------------------------------------------------------------------------

# Maps (module_path, class_name) → ToolSet subclass.
# Populated by register_toolset; read by _get_toolset from generated ObjectScript.
_registry: dict[tuple[str, str], type] = {}


# ---------------------------------------------------------------------------
# Public runtime helpers — called FROM generated ObjectScript via ##class(%SYS.Python)
# ---------------------------------------------------------------------------

def _get_toolset(module_path: str, class_name: str) -> ToolSet:
    """Return a fresh ToolSet instance for ObjectScript dispatch.

    Called by generated ObjectScript:
        Set tTs = tBridge."_get_toolset"("my_module", "MyTools")

    Lookup order:
    1. Process-level _registry (populated by register_toolset in this process).
    2. Module attribute _bridge_classes[class_name] (injected by register_toolset
       into the caller's module — survives cross-process via module re-import).
    3. Direct import of module_path and getattr by class_name (works when the
       class is defined at module level, not inside a factory function).
    """
    key = (module_path, class_name)
    cls = _registry.get(key)
    if cls is not None:
        return cls()

    # Try _bridge_classes injected into the module
    import importlib
    try:
        mod = importlib.import_module(module_path)
        bridge_classes = getattr(mod, "_bridge_classes", {})
        cls = bridge_classes.get(class_name)
        if cls is not None:
            _registry[key] = cls  # cache for this process
            return cls()
    except Exception:
        pass

    # Direct attribute lookup (works if class is at module level)
    try:
        if cls is None:
            cls = getattr(mod, class_name, None)
        if cls is not None:
            _registry[key] = cls
            return cls()
    except Exception:
        pass

    raise RuntimeError(
        f"ToolSet '{class_name}' from '{module_path}' not found. "
        f"Ensure register_toolset() was called or '{module_path}._bridge_classes[\"{class_name}\"]' exists."
    )


def _call_tool(toolset_instance: ToolSet, tool_name: str, args_json: str) -> str:
    """
    Dispatch a tool call from generated ObjectScript back to a Python ToolSet.

    Called as: tBridge."_call_tool"(tTs, "tool_name", tArgs.%ToJSON())
    where tArgs is a %DynamicArray of positional argument values.

    Returns a JSON string (object or plain value wrapped in {"result":...}).
    """
    try:
        args_list = json.loads(args_json) if args_json else []

        # get_catalog() gives us parameter order — use it to build kwargs
        catalog = toolset_instance.get_catalog()
        spec = next((t for t in catalog if t["name"] == tool_name), None)
        if spec is None:
            return json.dumps({"error": f"Tool '{tool_name}' not found in catalog"})

        param_names = list(spec.get("parameters", {}).get("properties", {}).keys())
        kwargs = dict(zip(param_names, args_list))

        raw = toolset_instance.execute(tool_name, kwargs)

        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                return json.dumps(parsed) if not isinstance(parsed, dict) else raw
            except (json.JSONDecodeError, ValueError):
                return json.dumps({"result": raw})
        else:
            return json.dumps({"result": str(raw)})
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _py_type_to_cls(py_type: str) -> str:
    """Map JSON-schema type string to ObjectScript parameter type."""
    return {
        "string": "%String",
        "integer": "%Integer",
        "number": "%Numeric",
        "boolean": "%Boolean",
    }.get(py_type, "%String")


def _to_os_method_name(snake: str) -> str:
    """Convert snake_case tool name to PascalCase ObjectScript method name."""
    return "".join(part.capitalize() for part in snake.split("_"))


def _to_os_param_name(snake: str) -> str:
    """Convert snake_case param name to pCamelCase ObjectScript parameter."""
    parts = snake.split("_")
    return "p" + parts[0].capitalize() + "".join(p.capitalize() for p in parts[1:])


def _build_tool_class(toolset_class: Type[ToolSet], module_path: str, module_dir: str = "") -> str:
    """Generate ObjectScript source for a %AI.Tool subclass."""
    ts = toolset_class()
    catalog = ts.get_catalog()
    class_name = f"Tmp.Bridge.{toolset_class.__name__}"
    toolset_name = toolset_class.__name__

    # Embed the module dir as a literal so the generated class is self-contained.
    # Falls back to mgr/../aicore/python/embedded if not supplied.
    if module_dir:
        path_expr = f'"{module_dir}"'
    else:
        path_expr = '##class(%File).GetDirectory($ZUtil(12)) _ "../aicore/python/embedded"'

    lines = [
        f'Include (%AI, %occStatus)',
        f'',
        f'/// Auto-generated bridge: {toolset_name} Python ToolSet → ObjectScript %AI.Tool',
        f'/// Generated by iris_tool_bridge.py — do not edit manually.',
        f'Class {class_name} Extends %AI.Tool',
        f'{{',
        f'',
        f'Property Name As %String [ InitialExpression = "{toolset_name}" ];',
        f'Property Description As %String(MAXLEN = "") '
        f'[ InitialExpression = "Python-bridged tools from {toolset_name}" ];',
        f'',
    ]

    for tool_spec in catalog:
        tool_name = tool_spec["name"]
        description = tool_spec.get("description", "")
        params_schema = tool_spec.get("parameters", {})
        properties = params_schema.get("properties", {})
        required = set(params_schema.get("required", []))

        # Build ObjectScript formal spec: pParamName As %Type = "default"
        formal_parts = []
        call_args = []
        for param_name, param_schema in properties.items():
            os_type = _py_type_to_cls(param_schema.get("type", "string"))
            os_param = _to_os_param_name(param_name)
            default = param_schema.get("default")
            if param_name not in required and default is not None:
                if os_type in ("%String",):
                    formal_parts.append(f'{os_param} As {os_type} = "{default}"')
                else:
                    formal_parts.append(f'{os_param} As {os_type} = {default}')
            else:
                formal_parts.append(f'{os_param} As {os_type}')
            call_args.append((param_name, os_param))

        formal_spec = ", ".join(formal_parts)
        method_name = _to_os_method_name(tool_name)

        # Build positional arg push list for the bridge helper
        arg_value_parts = []
        for py_name, os_name in call_args:
            arg_value_parts.append(f'    Do tArgs.%Push({os_name})')

        lines += [
            f'/// {description}',
            f'ClassMethod {method_name}({formal_spec}) As %DynamicObject',
            f'{{',
            f'    Set tSC = $$$OK',
            f'    Try {{',
            f'        // Ensure module dir is on sys.path, then import bridge + get toolset instance.',
            f'        // ##class(%SYS.Python).Import() caches within the process — no overhead on repeat calls.',
            f'        Set tSys = ##class(%SYS.Python).Import("sys")',
            f'        Do tSys.path.insert(0, {path_expr})',
            f'',
            f'        Set tBridge = ##class(%SYS.Python).Import("iris_tool_bridge")',
            f'        // _get_toolset retrieves from the bridge registry (populated by register_toolset)',
            f'        Set tTs = tBridge."_get_toolset"("{module_path}", "{toolset_name}")',
            f'',
            f'        // Pass args as a JSON array; bridge helper unpacks to kwargs',
            f'        Set tArgs = []',
        ]
        lines += [f'    {line}' for line in arg_value_parts]
        lines += [
            f'        Set tRaw = tBridge."_call_tool"(tTs, "{tool_name}", tArgs.%ToJSON())',
            f'',
            f'        // Coerce result to %DynamicObject',
            f'        Set tStr = tRaw _ ""',
            f'        Try {{',
            f'            Set tResult = ##class(%DynamicAbstractObject).%FromJSON(tStr)',
            f'            If $IsObject(tResult) && (tResult.%IsA("%DynamicObject") = 0) {{',
            f'                Set tResult = {{"result": (tStr)}}',
            f'            }}',
            f'        }} Catch {{ Set tResult = {{"result": (tStr)}} }}',
            f'',
            f'    }} Catch ex {{',
            f'        Set tSC = ex.AsStatus()',
            f'        Set tResult = {{"error": ($System.Status.GetErrorText(tSC))}}',
            f'    }}',
            f'    Return tResult',
            f'}}',
            f'',
        ]

    lines.append('}')
    return "\n".join(lines)


def _build_toolset_wrapper(toolset_class: Type[ToolSet]) -> str:
    """Generate a thin %AI.ToolSet XData wrapper that includes the bridge Tool."""
    toolset_name = toolset_class.__name__
    tool_class = f"Tmp.Bridge.{toolset_name}"
    wrapper_class = f"Tmp.Bridge.{toolset_name}ToolSet"

    return textwrap.dedent(f"""\
        /// Auto-generated %AI.ToolSet wrapper for {toolset_name} Python bridge.
        Class {wrapper_class} Extends %AI.ToolSet [ DependsOn = {tool_class} ]
        {{
        XData Definition [ MimeType = application/xml ]
        {{
          <ToolSet Name="{toolset_name}">
            <Description>Python-bridged ToolSet: {toolset_name}</Description>
            <Include Class="{tool_class}" />
          </ToolSet>
        }}
        }}
    """)


def _compile_cls(source: str, namespace: str = "") -> str:
    """Compile ObjectScript class source into IRIS. Returns the class name."""
    try:
        import iris
    except ImportError:
        raise RuntimeError(
            "iris module not available — register_toolset requires embedded Python "
            "(##class(%SYS.Python), not standalone irispython)"
        )

    import re
    m = re.search(r'^Class\s+(\S+)\s+Extends', source, re.MULTILINE)
    if not m:
        raise ValueError("Could not find class name in generated source")
    class_name = m.group(1)

    # Write source to a temp stream and compile via %SYSTEM.OBJ.LoadStream
    stream = iris.cls("%Stream.TmpCharacter")._New()
    stream.Write(source)
    errors_ref = iris.cls("%Library.ListOfObjects")._New()
    result = iris.cls("%SYSTEM.OBJ").LoadStream(stream, "ck", errors_ref)

    if iris.cls("%SYSTEM.Status").IsError(result):
        err = iris.cls("%SYSTEM.Status").GetErrorText(result)
        raise RuntimeError(f"Compile failed for {class_name}: {err}")

    return class_name


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def register_toolset(
    toolset_class: Type[ToolSet],
    module_path: str = "embedded_qa",
    module_dir: str = "",
    namespace: str = "",
) -> str:
    """
    Generate, compile, and register a Python ToolSet as an IRIS %AI.ToolSet.

    Args:
        toolset_class: The iris_llm ToolSet subclass to bridge.
        module_path: Python module name where toolset_class is defined.
        module_dir: Absolute path to the directory containing module_path.
                    Embedded in the generated ObjectScript so it's self-contained.
                    Defaults to a mgr-relative heuristic if omitted.
        namespace: IRIS namespace to compile into (default: current namespace).

    Returns:
        The ObjectScript class name of the generated %AI.ToolSet wrapper,
        e.g. "Tmp.Bridge.MyToolsToolSet". Use this in agents or MCP services.
    """
    tool_src = _build_tool_class(toolset_class, module_path, module_dir)
    wrapper_src = _build_toolset_wrapper(toolset_class)

    # Register in the process-level registry so generated ObjectScript can
    # retrieve the class via _get_toolset() without re-importing the caller's module.
    _registry[(module_path, toolset_class.__name__)] = toolset_class

    # Also inject into the caller's module as _bridge_classes so the registry
    # survives cross-process: when ObjectScript calls _get_toolset in a fresh
    # IRIS terminal session, it re-imports the module and finds the class there.
    import importlib
    try:
        mod = importlib.import_module(module_path)
        if not hasattr(mod, "_bridge_classes"):
            mod._bridge_classes = {}
        mod._bridge_classes[toolset_class.__name__] = toolset_class
    except Exception:
        pass  # non-fatal — process-level registry is the primary path

    try:
        import iris
        _iris_available = True
    except ImportError:
        _iris_available = False

    if _iris_available:
        _compile_cls(tool_src, namespace)
        wrapper_name = _compile_cls(wrapper_src, namespace)
        return wrapper_name
    else:
        # Dry-run mode: print generated source (useful for testing outside IRIS)
        print("=== Generated %AI.Tool source ===")
        print(tool_src)
        print()
        print("=== Generated %AI.ToolSet wrapper ===")
        print(wrapper_src)
        return f"Tmp.Bridge.{toolset_class.__name__}ToolSet"


def preview_toolset(toolset_class: Type[ToolSet], module_path: str = "embedded_qa") -> None:
    """Print the generated ObjectScript source without compiling. For inspection."""
    print("=== Generated %AI.Tool ===")
    print(_build_tool_class(toolset_class, module_path))
    print()
    print("=== Generated %AI.ToolSet wrapper ===")
    print(_build_toolset_wrapper(toolset_class))
