Include %occStatus

/// Business Process for CareConnectTrace E2E example.
/// Extends OTelBusinessProcess — OnRequest is automatically instrumented.
/// Returns TraceparentOut in the response so E2E tests can assert span wiring.
Class Sample.Interop.Examples.CareConnectBP Extends Sample.Interop.OTelBusinessProcess
{

Method OnHandleRequest(pRequest As %Persistent, Output pResponse As %Persistent) As %Status
{
    Set tSC = $$$OK
    Set pResponse = ##class(Sample.Interop.Examples.CareConnectResponse).%New()
    Set pResponse.Traceparent = ..TraceparentOut
    Quit tSC
}

}
