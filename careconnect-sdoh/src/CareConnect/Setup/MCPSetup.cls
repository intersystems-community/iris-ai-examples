/// Registers the CareConnect MCP service and seeds demo data.
/// Called by zpm module.xml after compilation.
Class CareConnect.Setup.MCPSetup Extends %RegisteredObject
{

ClassMethod Run() As %Status
{
    New $NAMESPACE
    Set $NAMESPACE = "%SYS"
    Do ##class(Security.Applications).Delete("/mcp/careconnect")
    Kill props
    Set props("DispatchClass") = "CareConnect.MCP.Service"
    Set props("AutheEnabled")  = 64
    Set props("Type")          = 18
    Set props("NameSpace")     = "IRISAPP"
    Set props("MatchRoles")    = ":%All"
    Set props("Recurse")       = 1
    Set props("Enabled")       = 1
    Set sc = ##class(Security.Applications).Create("/mcp/careconnect", .props)
    If $$$ISERR(sc) {
        Write "ERROR creating /mcp/careconnect: ", $System.Status.GetErrorText(sc), !
        Quit sc
    }
    Write "MCP Service /mcp/careconnect created.", !

    Set $NAMESPACE = "IRISAPP"
    Set sc = ##class(CareConnect.Setup.DemoData).Load()
    If $$$ISERR(sc) Write "WARN seeding demo data: ", $System.Status.GetErrorText(sc), !

    Set startSC = ##class(Ens.Director).StartProduction("CareConnect.Production")
    If $$$ISERR(startSC) Write "WARN starting production: ", $System.Status.GetErrorText(startSC), !
    Else  Write "CareConnect.Production started.", !

    Set mgr = ##class(%AI.ToolMgr).GetOrCreate("/mcp/careconnect", .isNew)
    Set sc2 = ##class(%AI.MCP.Service).LoadToolSetsToManager(mgr, "CareConnect.Tools.SDoHToolSet")
    Write "Tool discovery cache populated: ", $System.Status.IsOK(sc2), !

    Quit $$$OK
}

}
