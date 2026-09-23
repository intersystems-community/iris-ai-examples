Include %occStatus

/// Unit tests for Sample.Interop.OTelInteropAttrs.
Class Sample.Interop.Tests.TestOTelInteropAttrs Extends %UnitTest.TestCase
{

Property HeaderId As %String;

Method OnAfterOneTest() As %Status
{
    If ..HeaderId '= "" { Do ##class(Ens.MessageHeader).%DeleteId(..HeaderId) }
    Set ..HeaderId = ""
    Quit $$$OK
}

/// A span from a tracer; %Trace.Span.%New() returns "" outside the tracer.
Method NewSpan() As %Trace.Span
{
    Do ##class(Sample.Interop.OTelSetup).InitProvider("test-attrs")
    Quit ##class(%Trace.Provider).GetTracerProvider().GetTracer("test", "1.0").StartSpan("attrs")
}

/// Host and session attributes are set; the Visual Trace path names the session.
Method TestHostAttributes()
{
    Set tSpan = ..NewSpan()
    Do ##class(Sample.Interop.OTelInteropAttrs).Apply(tSpan, "LookupBP", "Demo.AIHub.LookupBP", 48)
    Do $$$AssertEquals(tSpan.Attributes.GetAt("messaging.destination.name"), "LookupBP")
    Do $$$AssertEquals(tSpan.Attributes.GetAt("messaging.message.conversation_id"), 48)
    Do $$$AssertEquals(tSpan.Attributes.GetAt("iris.interop.config_name"), "LookupBP")
    Do $$$AssertEquals(tSpan.Attributes.GetAt("iris.interop.host_class"), "Demo.AIHub.LookupBP")
    Do $$$AssertEquals(tSpan.Attributes.GetAt("iris.interop.session_id"), 48)
    Do $$$AssertEquals(tSpan.Attributes.GetAt("iris.interop.visual_trace"), "/ui/interop/message-viewer/index.html?$NAMESPACE="_$Namespace_"&SESSIONID=48")
    Do $$$AssertNotTrue(tSpan.Attributes.IsDefined("messaging.message.id"), "no header, no message id")
}

/// Header attributes match the Ens.MessageHeader the host is handling.
Method TestHeaderAttributes()
{
    Set tHdr = ##class(Ens.MessageHeader).%New()
    Set tHdr.SessionId = 48
    Set tHdr.SourceConfigName = "ToolService"
    Set tHdr.TargetConfigName = "LookupBP"
    Set tHdr.MessageBodyClassName = "Ens.StringRequest"
    Set tHdr.MessageBodyId = "17"
    Do $$$AssertStatusOK(tHdr.%Save(), "header saved")
    Set ..HeaderId = tHdr.%Id()
    Set tSpan = ..NewSpan()
    Do ##class(Sample.Interop.OTelInteropAttrs).Apply(tSpan, "LookupBP", "Demo.AIHub.LookupBP", 48, tHdr)
    Do $$$AssertEquals(tSpan.Attributes.GetAt("messaging.message.id"), ..HeaderId)
    Do $$$AssertEquals(tSpan.Attributes.GetAt("iris.interop.header_id"), ..HeaderId)
    Do $$$AssertEquals(tSpan.Attributes.GetAt("iris.interop.source"), "ToolService")
    Do $$$AssertEquals(tSpan.Attributes.GetAt("iris.interop.target"), "LookupBP")
    Do $$$AssertEquals(tSpan.Attributes.GetAt("iris.interop.body_class"), "Ens.StringRequest")
    Do $$$AssertEquals(tSpan.Attributes.GetAt("iris.interop.body_id"), "17")
}

/// Outside a production (empty config, session, header) nothing is set and nothing fails.
Method TestEmptyValuesSkipped()
{
    Set tSpan = ..NewSpan()
    Do ##class(Sample.Interop.OTelInteropAttrs).Apply(tSpan, "", "Sample.Interop.Tests.StubBO", "", "")
    Do $$$AssertEquals(tSpan.Attributes.GetAt("iris.interop.host_class"), "Sample.Interop.Tests.StubBO")
    Do $$$AssertNotTrue(tSpan.Attributes.IsDefined("iris.interop.session_id"), "no session id")
    Do $$$AssertNotTrue(tSpan.Attributes.IsDefined("iris.interop.visual_trace"), "no visual trace")
    Do $$$AssertNotTrue(tSpan.Attributes.IsDefined("messaging.destination.name"), "no config name")
}

}
