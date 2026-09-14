Include %occStatus

/// OTel-instrumented base class for IRIS Interoperability BusinessServices.
/// Wraps OnProcessInput with a bs.<ClassName> span. Extracts inbound traceparent
/// from ^IRIS.Temp.MsgTraceparent($Job) or an adapter-supplied headers array.
/// When an inbound traceparent is present, the BS span is a child of that trace.
Class Sample.Interop.OTelBusinessService Extends Ens.BusinessService
{

Property TraceparentIn As %String(MAXLEN = 64);
Property TraceparentOut As %String(MAXLEN = 64);

/// Override OnProcessInput to wrap with a %Trace span.
/// When no TracerProvider is initialized, delegates directly to subclass (noop).
Method OnProcessInput(pInput As %RegisteredObject, Output pOutput As %RegisteredObject, pHint As %String = "") As %Status
{
    Set tSC = $$$OK
    If '##class(%Trace.Provider).IsDefined() {
        Set tSC = ..OnHandleInput(pInput, .pOutput, pHint)
        Quit tSC
    }
    Set tCtx = ##class(%Trace.Context).GetCurrentContext()
    Set tTraceparent = $Get(^IRIS.Temp.MsgTraceparent($Job))
    If tTraceparent '= "" { Set tHdrs("traceparent") = tTraceparent }
    Set tParentCtx = ##class(%Trace.Propagation).HttpExtract(.tHdrs, tCtx)
    Set ..TraceparentIn = tTraceparent
    Set tTracer = ##class(%Trace.Provider).GetTracerProvider().GetTracer("iris.interop", "1.0")
    Set tAttrs("messaging.system")      = "intersystems_interop"
    Set tAttrs("messaging.destination") = ..%ClassName(1)
    Set tAttrs("messaging.operation")   = "receive"
    Set tSpan  = tTracer.StartSpan("bs." _ ..%ClassName(0), tParentCtx, "Server", .tAttrs)
    Set tScope = tTracer.SetActiveSpan(tSpan)
    Set ..TraceparentOut = tSpan.Context.ToString()
    Set ^IRIS.Temp.MsgTraceparent($Job) = ..TraceparentOut
    Try {
        Set tSC = ..OnHandleInput(pInput, .pOutput, pHint)
        If $$$ISOK(tSC) { Do tSpan.SetStatus("Ok") }
        Else             { Do tSpan.SetStatus("Error") }
    } Catch tEx {
        Do tSpan.SetStatus("Error")
        Do tSpan.End()
        Kill tScope
        Kill ^IRIS.Temp.MsgTraceparent($Job)
        Throw tEx
    }
    Do tSpan.End()
    Kill tScope
    Kill ^IRIS.Temp.MsgTraceparent($Job)
    Quit tSC
}

/// Subclasses override OnHandleInput (not OnProcessInput) to implement ingest logic.
Method OnHandleInput(pInput As %RegisteredObject, Output pOutput As %RegisteredObject, pHint As %String = "") As %Status
{
    Quit $$$OK
}

}
