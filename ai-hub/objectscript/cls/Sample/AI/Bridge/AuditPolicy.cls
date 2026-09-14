Include (%AI, %occStatus)

/// OTel audit policy for bridge-compiled Python toolsets.
///
/// Extends OTelAuditPolicy to tag all tool_call spans with
/// gen_ai.tool.source=python_bridge so they are visually distinct
/// in Jaeger/Grafana from native ObjectScript tool spans.
///
/// Attach via %GetAuditPolicy() on any %AI.ToolSet:
///
///   Method %GetAuditPolicy() As %AI.Policy.Audit
///   {
///       Return ##class(Sample.AI.Bridge.AuditPolicy).%New()
///   }
///
/// Or set on the agent directly:
///   Set tAgent.AuditPolicy = ##class(Sample.AI.Bridge.AuditPolicy).%New()
///
/// All OTEL_* env vars from OTelAuditPolicy apply here too.
Class Sample.AI.Bridge.AuditPolicy Extends Sample.AI.Policies.OTelAuditPolicy
{

Method %LogExecution(call As %DynamicObject, metadata As %DynamicObject, result As %DynamicObject, duration As %Integer, status As %Status) As %Status
{
    Set tSC = $$$OK
    Try {
        // Inject bridge source tag into the call metadata before parent logs
        If '$IsObject(metadata) { Set metadata = {} }
        Do metadata.%Set("gen_ai.tool.source", "python_bridge")
        Set tSC = ##super(call, metadata, result, duration, status)
    } Catch {
        // Never propagate
    }
    Return tSC
}

Method %LogDenial(call As %DynamicObject, metadata As %DynamicObject, status As %Status) As %Status
{
    Set tSC = $$$OK
    Try {
        If '$IsObject(metadata) { Set metadata = {} }
        Do metadata.%Set("gen_ai.tool.source", "python_bridge")
        Set tSC = ##super(call, metadata, status)
    } Catch {
    }
    Return tSC
}

}
