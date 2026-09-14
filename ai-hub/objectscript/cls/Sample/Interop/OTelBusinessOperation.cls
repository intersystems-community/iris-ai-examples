Include %occStatus

/// OTel-instrumented base class for IRIS Interoperability BusinessOperations.
/// Wraps OnMessage with a bo.<ClassName> span and injects traceparent into
/// outbound %Net.HttpRequest headers for cross-service context propagation.
Class Sample.Interop.OTelBusinessOperation Extends Ens.BusinessOperation
{

Property TraceparentIn As %String(MAXLEN = 64);
Property TraceparentOut As %String(MAXLEN = 64);

/// Override OnMessage to wrap with a %Trace span and inject traceparent into outbound HTTP.
/// When no TracerProvider is initialized, delegates directly to the subclass OnMessage (noop).
Method OnMessage(pRequest As %Library.Persistent, Output pResponse As %Library.Persistent) As %Status
{
    Set tSC = $$$OK
    If '##class(%Trace.Provider).IsDefined() {
        Set tSC = ..OnProcessMessage(pRequest, .pResponse)
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
    Set tAttrs("messaging.operation")   = "send"
    Set tSpan  = tTracer.StartSpan("bo." _ ..%ClassName(0), tParentCtx, "Client", .tAttrs)
    Set tScope = tTracer.SetActiveSpan(tSpan)
    Set ..TraceparentOut = tSpan.Context.ToString()
    Set ^IRIS.Temp.MsgTraceparent($Job) = ..TraceparentOut
    Try {
        Set tSC = ..OnProcessMessage(pRequest, .pResponse)
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

/// Subclasses override OnProcessMessage (not OnMessage) to implement outbound logic.
/// Within OnProcessMessage, call HttpRequestInject to propagate context into %Net.HttpRequest:
///   Do ##class(%Trace.Propagation).HttpRequestInject(pHttpReq, ##class(%Trace.Context).GetCurrentContext())
Method OnProcessMessage(pRequest As %Library.Persistent, Output pResponse As %Library.Persistent) As %Status
{
    Quit $$$OK
}

}
