Include %occStatus

/// Adapterless BS the tool invokes in-process. Its bs span parents on the tool span
/// through ^IRIS.Temp.MsgTraceparent($Job); it forwards its own context to the BP.
Class Demo.AIHub.ToolService Extends Sample.Interop.OTelBusinessService
{

Method OnHandleInput(pInput As %RegisteredObject, Output pOutput As %RegisteredObject, pHint As %String = "") As %Status
{
    Set tSC = $$$OK
    Set pInput.Traceparent = ..TraceparentOut
    Set tSC = ..SendRequestSync("LookupBP", pInput, .pOutput)
    Quit tSC
}

}
