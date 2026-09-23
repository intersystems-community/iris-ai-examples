Include %occStatus

/// Interop identifiers for bs/bp/bo spans, so a span can be matched to its Visual Trace
/// session and message header. iris.interop.visual_trace opens the session in the
/// Message Viewer UI (/ui/interop/message-viewer). Uses OTel messaging names where one
/// exists, iris.interop.* otherwise. Empty values are skipped (a host run outside a
/// production has none).
Class Sample.Interop.OTelInteropAttrs Extends %RegisteredObject
{

/// Set the attributes on pSpan. pHeader is the Ens.MessageHeader the host is handling,
/// or "" when there is none.
ClassMethod Apply(pSpan As %Trace.Span, pConfigName As %String, pHostClass As %String, pSessionId As %String, pHeader As Ens.MessageHeader = "")
{
    Do pSpan.Attributes.SetAt(pHostClass, "iris.interop.host_class")
    If pConfigName '= "" {
        Do pSpan.Attributes.SetAt(pConfigName, "messaging.destination.name")
        Do pSpan.Attributes.SetAt(pConfigName, "iris.interop.config_name")
    }
    If pSessionId '= "" {
        Do pSpan.Attributes.SetAt(pSessionId, "messaging.message.conversation_id")
        Do pSpan.Attributes.SetAt(pSessionId, "iris.interop.session_id")
        Do pSpan.Attributes.SetAt("/ui/interop/message-viewer/index.html?$NAMESPACE="_$Namespace_"&SESSIONID="_pSessionId, "iris.interop.visual_trace")
    }
    Set tProduction = $Get(^Ens.Runtime("Name"))
    If tProduction '= "" { Do pSpan.Attributes.SetAt(tProduction, "iris.interop.production") }
    If '$IsObject(pHeader) Quit
    Set tHeaderId = pHeader.%Id()
    If tHeaderId '= "" {
        Do pSpan.Attributes.SetAt(tHeaderId, "messaging.message.id")
        Do pSpan.Attributes.SetAt(tHeaderId, "iris.interop.header_id")
    }
    Do pSpan.Attributes.SetAt(pHeader.SourceConfigName, "iris.interop.source")
    Do pSpan.Attributes.SetAt(pHeader.TargetConfigName, "iris.interop.target")
    Do pSpan.Attributes.SetAt(pHeader.MessageBodyClassName, "iris.interop.body_class")
    Do pSpan.Attributes.SetAt(pHeader.MessageBodyId, "iris.interop.body_id")
}

}
