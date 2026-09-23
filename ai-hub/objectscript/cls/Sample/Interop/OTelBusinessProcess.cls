Include %occStatus

/// OTel-instrumented base class for IRIS Interoperability BusinessProcesses.
/// Replace "Extends Ens.BusinessProcess" with "Extends Sample.Interop.OTelBusinessProcess"
/// to get per-message messaging.* OTel spans with zero additional code.
///
/// Prerequisites:
///   1. Call Sample.Interop.OTelSetup.InitProvider("my-service") from production OnStart.
///   2. Ens.* classes require a HealthShare / IRIS for Health image.
///
/// OTelPolicy linkage (optional):
///   Set ..OTelPolicy = myOTelAuditPolicyInstance before dispatching an AI agent.
///   The BP span's traceparent is written to OTelPolicy.Traceparent so agent tool-call
///   spans become children of the BP span in the unified trace.
Class Sample.Interop.OTelBusinessProcess Extends Ens.BusinessProcess
{

/// Optional: link to an OTelAuditPolicy so AI agent spans are children of this BP span.
Property OTelPolicy As Sample.AI.Policies.OTelAuditPolicy;

/// W3C traceparent extracted from the inbound message (for inspection/chaining).
Property TraceparentIn As %String(MAXLEN = 64);

/// W3C traceparent of the span started for this message (for downstream propagation).
Property TraceparentOut As %String(MAXLEN = 64);

/// Override OnRequest to wrap OnHandleRequest with a %Trace span.
/// When no TracerProvider is initialized, delegates directly to OnHandleRequest (noop).
Method OnRequest(pRequest As %Persistent, Output pResponse As %Persistent) As %Status
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
    Do ##class(Sample.Interop.OTelInteropAttrs).Apply(tSpan, ..%ConfigName, ..%ClassName(1), ..%SessionId, ..%PrimaryRequestHeader)
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

/// Subclasses override OnHandleRequest (not OnRequest) to implement message handling.
Method OnHandleRequest(pRequest As %Persistent, Output pResponse As %Persistent) As %Status
{
    Quit $$$OK
}

}
