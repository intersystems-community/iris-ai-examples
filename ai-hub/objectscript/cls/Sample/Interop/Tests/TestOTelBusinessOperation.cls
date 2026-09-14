Include %occStatus

/// Unit tests for Sample.Interop.OTelBusinessOperation.
Class Sample.Interop.Tests.TestOTelBusinessOperation Extends %UnitTest.TestCase
{

Method OnBeforeOneTest() As %Status
{
    Kill ^IRIS.Temp.TracerProvider($Namespace)
    Kill ^IRIS.Temp.MsgTraceparent($Job)
    Quit $$$OK
}

/// With provider, OnMessage must emit a span and set TraceparentOut.
Method TestSpanEmitted()
{
    Do ##class(Sample.Interop.OTelSetup).InitProvider("test-bo")
    Set tBO = ##class(Sample.Interop.Tests.StubBO).%New()
    Set tReq = ##class(Ens.StringRequest).%New()
    Set tSC = tBO.OnMessage(tReq, .tResp)
    Do $$$AssertStatusOK(tSC, "OnMessage succeeds")
    Do $$$AssertTrue(tBO.TraceparentOut '= "", "TraceparentOut non-empty")
    Do $$$AssertEquals($Extract(tBO.TraceparentOut, 1, 3), "00-", "TraceparentOut W3C format")
}

/// HttpRequestInject must set traceparent header on a %Net.HttpRequest.
Method TestHeaderInjected()
{
    Do ##class(Sample.Interop.OTelSetup).InitProvider("test-bo")
    Set tBO = ##class(Sample.Interop.Tests.StubBO).%New()
    Set tReq = ##class(Ens.StringRequest).%New()
    Do tBO.OnMessage(tReq, .tResp)
    Do $$$AssertTrue(tBO.CapturedTraceparent '= "", "traceparent injected into outbound request")
    Do $$$AssertEquals($Extract(tBO.CapturedTraceparent, 1, 3), "00-", "injected traceparent is W3C format")
}

/// Without provider, OnMessage runs noop — TraceparentOut stays empty.
Method TestNoopWhenNoProvider()
{
    Set tBO = ##class(Sample.Interop.Tests.StubBO).%New()
    Set tReq = ##class(Ens.StringRequest).%New()
    Set tSC = tBO.OnMessage(tReq, .tResp)
    Do $$$AssertStatusOK(tSC, "noop succeeds")
    Do $$$AssertEquals(tBO.TraceparentOut, "", "TraceparentOut empty in noop")
}

}
