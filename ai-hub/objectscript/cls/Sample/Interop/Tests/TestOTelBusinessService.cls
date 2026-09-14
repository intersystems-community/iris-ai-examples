Include %occStatus

/// Unit tests for Sample.Interop.OTelBusinessService.
Class Sample.Interop.Tests.TestOTelBusinessService Extends %UnitTest.TestCase
{

Method OnBeforeOneTest() As %Status
{
    Kill ^IRIS.Temp.TracerProvider($Namespace)
    Kill ^IRIS.Temp.MsgTraceparent($Job)
    Quit $$$OK
}

/// With provider, OnProcessInput must emit a span and set TraceparentOut.
Method TestSpanEmitted()
{
    Do ##class(Sample.Interop.OTelSetup).InitProvider("test-bs")
    Set tBS = ##class(Sample.Interop.Tests.StubBS).%New()
    Set tSC = tBS.OnProcessInput(##class(Ens.StringRequest).%New(), .tOut)
    Do $$$AssertStatusOK(tSC, "OnProcessInput succeeds")
    Do $$$AssertTrue(tBS.TraceparentOut '= "", "TraceparentOut non-empty")
    Do $$$AssertEquals($Extract(tBS.TraceparentOut, 1, 3), "00-", "W3C format")
}

/// When ^IRIS.Temp.MsgTraceparent($Job) has a traceparent, BS span must be a child (same traceId).
Method TestExtractsInboundTraceparent()
{
    Do ##class(Sample.Interop.OTelSetup).InitProvider("test-bs")
    Set tFakeParent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    Set ^IRIS.Temp.MsgTraceparent($Job) = tFakeParent
    Set tBS = ##class(Sample.Interop.Tests.StubBS).%New()
    Do tBS.OnProcessInput(##class(Ens.StringRequest).%New(), .tOut)
    Do $$$AssertEquals(tBS.TraceparentIn, tFakeParent, "TraceparentIn captured from global")
    Set tParentTraceId = $ListGet($ListFromString(tFakeParent, "-"), 2)
    Set tChildTraceId  = $ListGet($ListFromString(tBS.TraceparentOut, "-"), 2)
    Do $$$AssertEquals(tParentTraceId, tChildTraceId, "BS span is child of inbound trace (same traceId)")
    Kill ^IRIS.Temp.MsgTraceparent($Job)
}

/// Without provider, OnProcessInput runs noop — TraceparentOut stays empty.
Method TestNoopWhenNoProvider()
{
    Set tBS = ##class(Sample.Interop.Tests.StubBS).%New()
    Set tSC = tBS.OnProcessInput(##class(Ens.StringRequest).%New(), .tOut)
    Do $$$AssertStatusOK(tSC, "noop succeeds")
    Do $$$AssertEquals(tBS.TraceparentOut, "", "TraceparentOut empty in noop")
}

}
