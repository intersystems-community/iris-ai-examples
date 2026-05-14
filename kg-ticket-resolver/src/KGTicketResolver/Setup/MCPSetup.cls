/// Sets up the MCP endpoint and tool registration for KGTicketResolver.
Class KGTicketResolver.Setup.MCPSetup Extends %RegisteredObject
{

ClassMethod Setup() As %Status
{
    // Create the MCP web application
    Set props("NameSpace")       = "USER"
    Set props("DispatchClass")   = "KGTicketResolver.MCP.Service"
    Set props("AutheEnabled")    = 96
    Set props("MatchRoles")      = ":%All"
    Set props("Recurse")         = 1
    Set props("Enabled")         = 1

    If ##class(Security.Applications).Exists("/mcp/kgtickets") {
        Write "MCP endpoint already exists.", !
    } Else {
        Set sc = ##class(Security.Applications).Create("/mcp/kgtickets", .props)
        Write $Select($$$ISOK(sc):"MCP endpoint created: /mcp/kgtickets", 1:"Error creating endpoint: "_$System.Status.GetErrorText(sc)), !
    }

    // Register tools
    Set mgr = ##class(%AI.ToolMgr).GetOrCreate("/mcp/kgtickets", .isNew)
    Do ##class(%AI.MCP.Service).LoadToolSetsToManager(mgr, "KGTicketResolver.Tools.ToolSet")
    Write "Tools registered: ", mgr.FindTools("").%Size(), !

    Quit $$$OK
}

}
