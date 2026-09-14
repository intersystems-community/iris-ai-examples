Include %occStatus

/// Unit tests for Sample.Interop.OTelBusinessProcess.
Class Sample.Interop.Tests.TestOTelBusinessProcess Extends %UnitTest.TestCase
{

Method OnBeforeOneTest() As %Status
{
    Kill ^IRIS.Temp.TracerProvider($Namespace)
    Kill ^IRIS.Temp.MsgTraceparent($Job)
    Quit $$$OK
}

/// When no TracerProvider is registered, OnRequest must run without error and TraceparentOut stays empty.
Method TestNoopWhenNoProvider()
{
    Set tBP = ##class(Sample.Interop.Tests.StubBP).%New()
    Set tReq = ##class(Ens.StringRequest).%New()
    Set tSC = tBP.OnRequest(tReq, .tResp)
    Do $$$AssertStatusOK(tSC, "OnRequest succeeds with no provider")
    Do $$$AssertEquals(tBP.TraceparentOut, "", "TraceparentOut empty when noop")
    Do $$$AssertEquals(tBP.ProcessInputCalled, 1, "OnHandleRequest was called")
}

/// When TracerProvider is initialized, OnRequest must set TraceparentOut to a non-empty W3C string.
Method TestSpanEmittedWhenProvider()
{
    Do ##class(Sample.Interop.OTelSetup).InitProvider("test-bp")
    Set tBP = ##class(Sample.Interop.Tests.StubBP).%New()
    Set tReq = ##class(Ens.StringRequest).%New()
    Set tSC = tBP.OnRequest(tReq, .tResp)
    Do $$$AssertStatusOK(tSC, "OnRequest succeeds with provider")
    Do $$$AssertTrue(tBP.TraceparentOut '= "", "TraceparentOut non-empty")
    Do $$$AssertEquals($Extract(tBP.TraceparentOut, 1, 3), "00-", "TraceparentOut is W3C format")
}

/// When ^IRIS.Temp.MsgTraceparent($Job) has a traceparent, TraceparentIn must capture it.
Method TestParentChainingViaGlobal()
{
    Do ##class(Sample.Interop.OTelSetup).InitProvider("test-bp")
    Set tFakeParent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    Set ^IRIS.Temp.MsgTraceparent($Job) = tFakeParent
    Set tBP = ##class(Sample.Interop.Tests.StubBP).%New()
    Set tReq = ##class(Ens.StringRequest).%New()
    Do tBP.OnRequest(tReq, .tResp)
    Do $$$AssertEquals(tBP.TraceparentIn, tFakeParent, "TraceparentIn captures global traceparent")
    Kill ^IRIS.Temp.MsgTraceparent($Job)
}

/// When OnHandleRequest throws, span must be ended and exception re-raised.
Method TestErrorSpanOnException()
{
    Do ##class(Sample.Interop.OTelSetup).InitProvider("test-bp")
    Set tBP = ##class(Sample.Interop.Tests.ThrowingBP).%New()
    Set tReq = ##class(Ens.StringRequest).%New()
    Set tCaught = 0
    Try {
        Do tBP.OnRequest(tReq, .tResp)
    } Catch tEx {
        Set tCaught = 1
    }
    Do $$$AssertEquals(tCaught, 1, "Exception propagated from OnHandleRequest")
    Do $$$AssertTrue(tBP.TraceparentOut '= "", "TraceparentOut set before exception (span ended)")
}

/// When OTelPolicy is set, its Traceparent must equal TraceparentOut after OnRequest.
Method TestOTelPolicyLinked()
{
    Do ##class(Sample.Interop.OTelSetup).InitProvider("test-bp")
    Set tBP = ##class(Sample.Interop.Tests.StubBP).%New()
    Set tPolicy = ##class(Sample.AI.Policies.OTelAuditPolicy).%New()
    Set tBP.OTelPolicy = tPolicy
    Set tReq = ##class(Ens.StringRequest).%New()
    Do tBP.OnRequest(tReq, .tResp)
    Do $$$AssertTrue(tPolicy.Traceparent '= "", "OTelPolicy.Traceparent set")
    Do $$$AssertEquals(tPolicy.Traceparent, tBP.TraceparentOut, "OTelPolicy.Traceparent = TraceparentOut")
}

}
