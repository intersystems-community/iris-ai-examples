Include %occStatus

/// Unit tests for Sample.Interop.OTelSetup.
Class Sample.Interop.Tests.TestOTelSetup Extends %UnitTest.TestCase
{

Method OnBeforeOneTest() As %Status
{
    Kill ^IRIS.Temp.TracerProvider($Namespace)
    Quit $$$OK
}

/// InitProvider should make IsDefined() return 1.
Method TestInitProviderSetsIsDefined()
{
    Do $$$AssertEquals(##class(%Trace.Provider).IsDefined(), 0, "cold namespace: IsDefined=0")
    Set tSC = ##class(Sample.Interop.OTelSetup).InitProvider("test-service")
    Do $$$AssertStatusOK(tSC, "InitProvider returns OK")
    Do $$$AssertTrue(##class(%Trace.Provider).IsDefined() > 0, "after init: IsDefined>0")
}

/// Second call to InitProvider must not error and must not reset provider.
Method TestInitProviderIdempotent()
{
    Set tSC1 = ##class(Sample.Interop.OTelSetup).InitProvider("test-service")
    Set tSC2 = ##class(Sample.Interop.OTelSetup).InitProvider("test-service")
    Do $$$AssertStatusOK(tSC1, "first call OK")
    Do $$$AssertStatusOK(tSC2, "second call OK (idempotent)")
    Do $$$AssertTrue(##class(%Trace.Provider).IsDefined() > 0, "IsDefined>0 after second call")
}

/// GetTracerProvider().GetTracer() must return a real %Trace.Tracer OREF after init.
Method TestGetTracerAfterInit()
{
    Do ##class(Sample.Interop.OTelSetup).InitProvider("test-service")
    Set tTracer = ##class(%Trace.Provider).GetTracerProvider().GetTracer("test", "1.0")
    Do $$$AssertEquals($IsObject(tTracer), 1, "GetTracer returns non-empty OREF")
    Do $$$AssertEquals(tTracer.%ClassName(1), "%Trace.Tracer", "OREF is %Trace.Tracer")
}

/// IsProviderReady should reflect IsDefined.
Method TestIsProviderReady()
{
    Do $$$AssertEquals(##class(Sample.Interop.OTelSetup).IsProviderReady(), 0, "cold: IsProviderReady=0")
    Do ##class(Sample.Interop.OTelSetup).InitProvider("test-service")
    Do $$$AssertTrue(##class(Sample.Interop.OTelSetup).IsProviderReady() > 0, "after init: IsProviderReady>0")
}

}
