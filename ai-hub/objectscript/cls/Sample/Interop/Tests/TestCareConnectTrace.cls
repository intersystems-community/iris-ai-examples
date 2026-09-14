Include %occStatus

/// E2E integration test for CareConnectTrace.
/// Starts a real Ens production, drives a message through BS→BP→BO,
/// and asserts that OTel span wiring produced a non-empty W3C traceparent.
Class Sample.Interop.Tests.TestCareConnectTrace Extends %UnitTest.TestCase
{

Method OnBeforeAllTests() As %Status
{
    // Stop any running production to avoid conflicts
    If $Get(^Ens.Director("State")) '= "" {
        Do ##class(Ens.Director).StopProduction(10, 1)
    }
    Kill ^IRIS.Temp.TracerProvider($Namespace)
    Kill ^IRIS.Temp.MsgTraceparent($Job)
    Quit $$$OK
}

Method OnAfterAllTests() As %Status
{
    // Clean up — stop production started by tests
    If $Get(^Ens.Director("Production")) = "Sample.Interop.Examples.CareConnectProduction" {
        Do ##class(Ens.Director).StopProduction(10, 1)
    }
    Quit $$$OK
}

/// Start production, send one message, assert BP TraceparentOut is non-empty.
Method TestRunProducesTrace()
{
    Do ##class(Sample.Interop.OTelSetup).InitProvider("test-careconnect-e2e")

    Set tSC = ##class(Ens.Director).StartProduction(
        "Sample.Interop.Examples.CareConnectProduction")
    Do $$$AssertStatusOK(tSC, "StartProduction must succeed")
    If $$$ISERR(tSC) { Quit }

    Set tTraceparent = ##class(Sample.Interop.Examples.CareConnectTrace).SendOneMessage()

    Do ##class(Ens.Director).StopProduction(10, 1)

    Do $$$AssertNotEquals("", tTraceparent, "BP TraceparentOut must be non-empty")
    Do $$$AssertTrue($Length(tTraceparent) >= 55, "TraceparentOut must be W3C format (>=55 chars)")
    Do $$$AssertTrue(tTraceparent [ "00-", "TraceparentOut must begin with version 00-")
}

// The noop path is NOT tested here.
//
// It was, and it could never have worked: %New() on a real Ens business host
// returns a null OREF outside a running production (Ens.Host.%OnNew rejects a
// config name it cannot find), so the test died with <INVALID OREF> on the
// first OnRequest. It only ever looked green because the Python runner was
// passing a class name where %UnitTest.Manager wanted a directory and so ran
// nothing at all.
//
// Sample.Interop.Tests.TestOTelBusinessProcess:TestNoopWhenNoProvider covers
// the same contract properly, against StubBP — a %RegisteredObject that can be
// instantiated standalone. This suite is the live-production E2E; keep it to
// what only a production can prove.

}
