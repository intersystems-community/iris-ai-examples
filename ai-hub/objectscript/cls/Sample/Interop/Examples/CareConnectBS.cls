Include %occStatus

/// Stub Business Service for CareConnectTrace example.
/// Starts a root bs.* span and writes traceparent to ^IRIS.Temp.MsgTraceparent($Job)
/// for the downstream BP to pick up.
Class Sample.Interop.Examples.CareConnectBS Extends %RegisteredObject
{

/// Simulate inbound trigger: starts a bs.* span and propagates traceparent.
Method SimulateInput(pMsg As %DynamicObject) As %Status
{
    Set tSC = $$$OK
    If '##class(%Trace.Provider).IsDefined() { Quit tSC }
    Set tTracer = ##class(%Trace.Provider).GetTracerProvider().GetTracer("iris.interop", "1.0")
    Set tAttrs("messaging.system")      = "intersystems_interop"
    Set tAttrs("messaging.destination") = "CareConnectBS"
    Set tAttrs("messaging.operation")   = "receive"
    Set tSpan  = tTracer.StartSpan("bs.CareConnectBS", "", "Server", .tAttrs)
    Set tScope = tTracer.SetActiveSpan(tSpan)
    Set ^IRIS.Temp.MsgTraceparent($Job) = tSpan.Context.ToString()
    Do tSpan.SetStatus("Ok")
    Do tSpan.End()
    Kill tScope
    Quit tSC
}

}
