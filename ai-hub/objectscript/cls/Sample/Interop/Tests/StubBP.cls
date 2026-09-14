Include %occStatus

/// Testable stub for OTelBusinessProcess logic.
/// Extends %RegisteredObject (not Ens.BusinessProcess) so it can be instantiated
/// outside production context. Duplicates OnRequest span logic from OTelBusinessProcess
/// to keep unit tests self-contained.
Class Sample.Interop.Tests.StubBP Extends %RegisteredObject
{

Property OTelPolicy As Sample.AI.Policies.OTelAuditPolicy;
Property TraceparentIn As %String;
Property TraceparentOut As %String;
Property ProcessInputCalled As %Integer [ InitialExpression = 0 ];

Method OnRequest(pRequest As %RegisteredObject, Output pResponse As %RegisteredObject) As %Status
{
    Set tSC = $$$OK
    If '##class(%Trace.Provider).IsDefined() {
        Set tSC = ..OnHandleRequest(pRequest, .pResponse)
        Quit tSC
    }
    Set tCtx = ##class(%Trace.Context).GetCurrentContext()
    Set tTraceparent = $Get(^IRIS.Temp.MsgTraceparent($Job))
    If $IsObject(pRequest) {
        Try { Set tTraceparent = pRequest.Headers("traceparent") } Catch {}
    }
    If tTraceparent '= "" { Set tHdrs("traceparent") = tTraceparent }
    Set tParentCtx = ##class(%Trace.Propagation).HttpExtract(.tHdrs, tCtx)
    Set ..TraceparentIn = tTraceparent
    Set tTracer = ##class(%Trace.Provider).GetTracerProvider().GetTracer("iris.interop", "1.0")
    Set tAttrs("messaging.system")      = "intersystems_interop"
    Set tAttrs("messaging.destination") = ..%ClassName(1)
    Set tAttrs("messaging.operation")   = "process"
    Set tSpan  = tTracer.StartSpan("bp." _ ..%ClassName(0), tParentCtx, "Internal", .tAttrs)
    Set tScope = tTracer.SetActiveSpan(tSpan)
    Set ..TraceparentOut = tSpan.Context.ToString()
    If $IsObject(..OTelPolicy) { Set ..OTelPolicy.Traceparent = ..TraceparentOut }
    Try {
        Set tSC = ..OnHandleRequest(pRequest, .pResponse)
        If $$$ISOK(tSC) { Do tSpan.SetStatus("Ok") }
        Else             { Do tSpan.SetStatus("Error") }
    } Catch tEx {
        Do tSpan.SetStatus("Error")
        Do tSpan.End()
        Kill tScope
        Throw tEx
    }
    Do tSpan.End()
    Kill tScope
    Quit tSC
}

Method OnHandleRequest(pRequest As %RegisteredObject, Output pResponse As %RegisteredObject) As %Status
{
    Set ..ProcessInputCalled = ..ProcessInputCalled + 1
    Quit $$$OK
}

}
