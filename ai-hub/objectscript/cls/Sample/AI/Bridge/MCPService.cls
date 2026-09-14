Include (%AI, %occStatus)

/// MCP service that exposes a bridge-compiled Python ToolSet as an MCP endpoint.
///
/// External MCP clients (Claude Desktop, other AI Hub instances, custom agents)
/// can call the Python @tool functions over the MCP protocol — no Python runtime
/// needed on the client side.  The client sees standard MCP tool descriptors;
/// IRIS dispatches each call through the compiled ObjectScript wrapper back to
/// the irispython runtime.
///
/// The default SPECIFICATION is the IRISInfoTools demo ToolSet compiled by
/// bridge_xdev_demo.  Override it by subclassing:
///
///   Class My.Bridge.MyToolService Extends Sample.AI.Bridge.MCPService
///   {
///       Parameter SPECIFICATION = "Tmp.Bridge.MyToolsToolSet";
///   }
///
/// Or register at runtime — call SetupService() from a setup routine to
/// create the CSP application:
///
///   Do ##class(Sample.AI.Bridge.MCPService).SetupService(
///       "/api/bridge/mcp",
///       "Tmp.Bridge.IRISInfoToolsToolSet")
///
/// Endpoint (once CSP app registered):
///   http://<host>:<port>/api/bridge/mcp/mcp
///
/// The service enforces the bridge AuthPolicy (configurable deny/allow list)
/// and emits OTel spans via the bridge AuditPolicy.
Class Sample.AI.Bridge.MCPService Extends %AI.MCP.Service
{

/// Bridge-compiled ToolSet class name.
/// Default: the IRISInfoTools ToolSet compiled by bridge_xdev_demo.
/// Override this parameter in a subclass to expose any other bridge ToolSet.
Parameter SPECIFICATION As STRING = "Tmp.Bridge.IRISInfoToolsToolSet";

/// IRIS web server endpoint for display in setup output.
/// Override in a subclass when IRIS runs on a non-default host or port.
/// Example: "http://iris.internal:52773"
Parameter ENDPOINT As STRING = "http://localhost:52773";

/// Register a CSP application for this MCP service in the current namespace.
///
/// pPath         — URL path prefix, e.g. "/api/bridge/mcp"
/// pToolSetClass — override the ToolSet class (updates SPECIFICATION at registration)
///
/// After calling this, the endpoint is:
///   http://<host>:<port><pPath>/mcp
ClassMethod SetupService(
    pPath As %String = "/api/bridge/mcp",
    pToolSetClass As %String = "") As %Status
{
    Set tSC = $$$OK
    Try {
        Set tNS = $Namespace

        // Ensure the ToolSet class exists before registering
        Set tSpec = $Select(pToolSetClass '= "": pToolSetClass,
                            1: ..#SPECIFICATION)
        If tSpec '= "" && '##class(%Dictionary.CompiledClass).%ExistsId(tSpec) {
            Write "Warning: ToolSet class not found: ", tSpec, !
            Write "  Run bridge registration first, then call SetupService() again.", !
        }

        // Register the CSP application pointing to this service class
        Set tProps("NameSpace")       = tNS
        Set tProps("Enabled")         = 1
        Set tProps("IsNameSpaceDefault") = 0
        Set tProps("DispatchClass")   = $ClassName()

        Set tSC = ##class(%SYS.REST).AddApplication(pPath, .tProps)
        If $$$ISERR(tSC) {
            Write "Error registering CSP app: ", $System.Status.GetErrorText(tSC), !
            Return tSC
        }

        Write "MCP service registered:", !
        Write "  Path:     ", pPath, !
        Write "  ToolSet:  ", tSpec, !
        Write "  Endpoint: ", ..#ENDPOINT, pPath, "/mcp", !
    } Catch ex {
        Set tSC = ex.AsStatus()
        Write "Error: ", ex.DisplayString(), !
    }
    Return tSC
}

/// Convenience: print current registration status.
ClassMethod Status() As %Status
{
    Set tSC = $$$OK
    Try {
        Set tSpec = ..#SPECIFICATION
        Write "Sample.AI.Bridge.MCPService", !
        Write "  SPECIFICATION: ", tSpec, !
        If tSpec '= "" {
            Write "  ToolSet compiled: ",
                  $Select(##class(%Dictionary.CompiledClass).%ExistsId(tSpec): "YES",
                          1: "NO — run bridge registration first"), !
        }
    } Catch ex {
        Set tSC = ex.AsStatus()
    }
    Return tSC
}

}
