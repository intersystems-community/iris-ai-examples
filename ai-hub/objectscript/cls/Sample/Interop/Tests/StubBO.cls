Include %occStatus

/// Testable stub for OTelBusinessOperation logic.
/// Extends %RegisteredObject so it can be instantiated outside production context.
/// Duplicates OnMessage span logic from OTelBusinessOperation.
Class Sample.Interop.Tests.StubBO Extends %RegisteredObject
{

Property TraceparentIn As %String;
Property TraceparentOut As %String;
Property CapturedTraceparent As %String;

Method OnMessage(pRequest As %RegisteredObject, Output pResponse As %RegisteredObject) As %Status
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

Method OnProcessMessage(pRequest As %RegisteredObject, Output pResponse As %RegisteredObject) As %Status
{
    Set tHttpReq = ##class(%Net.HttpRequest).%New()
    Do ##class(%Trace.Propagation).HttpRequestInject(tHttpReq, ##class(%Trace.Context).GetCurrentContext())
    Set ..CapturedTraceparent = tHttpReq.GetHeader("traceparent")
    Quit $$$OK
}

}
