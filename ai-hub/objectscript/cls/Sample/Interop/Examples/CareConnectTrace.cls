Include %occStatus

/// Helper for CareConnectTrace E2E: initializes OTel and drives one message
/// through the test production, returning the BP span traceparent.
///
/// Requires the production to already be running (or use RunWithProduction).
Class Sample.Interop.Examples.CareConnectTrace Extends %RegisteredObject
{

/// Start production, run one traced message, stop production. Returns BP TraceparentOut.
/// Returns "" if %Trace not available.
ClassMethod RunWithProduction(pServiceName As %String = "careconnect-trace") As %String
{
    Set tSC = $$$OK
    Set tResult = ""

    Do ##class(Sample.Interop.OTelSetup).InitProvider(pServiceName)

    Set tSC = ##class(Ens.Director).StartProduction("Sample.Interop.Examples.CareConnectProduction")
    If $$$ISERR(tSC) { Quit "" }

    Try {
        Set tResult = ..SendOneMessage()
    } Catch tEx {
        Set tResult = ""
    }

    Do ##class(Ens.Director).StopProduction(10, 1)
    Quit tResult
}

/// Send one CareConnectRequest to CareConnectBP and return the response Traceparent.
ClassMethod SendOneMessage() As %String
{
    Set tReq = ##class(Sample.Interop.Examples.CareConnectRequest).%New()
    Set tReq.Payload = "ping"
    Set tSC = ##class(EnsLib.Testing.Service).SendTestRequest(
        "CareConnectBP", tReq, .tResp, .tSessionId, 1)
    If $$$ISERR(tSC) { Quit "" }
    If '$IsObject(tResp) { Quit "" }
    Quit tResp.Traceparent
}

}
