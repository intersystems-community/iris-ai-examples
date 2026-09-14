Include %occStatus

/// Testable stub for OTelBusinessService logic.
/// Extends %RegisteredObject so it can be instantiated outside production context.
/// Duplicates OnProcessInput span logic from OTelBusinessService.
Class Sample.Interop.Tests.StubBS Extends %RegisteredObject
{

Property TraceparentIn As %String;
Property TraceparentOut As %String;

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

Method OnHandleInput(pInput As %RegisteredObject, Output pOutput As %RegisteredObject, pHint As %String = "") As %Status
{
    Quit $$$OK
}

}
