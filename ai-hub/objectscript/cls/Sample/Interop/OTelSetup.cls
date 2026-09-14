Include %occStatus

/// TracerProvider init utility for IRIS Interoperability productions.
/// Call InitProvider() once from a production's OnStart override.
/// The provider is stored in ^IRIS.Temp.TracerProvider($namespace) — cleared on IRIS restart,
/// so wire InitProvider to OnStart rather than relying on it persisting.
Class Sample.Interop.OTelSetup Extends %RegisteredObject
{

/// Initialize the %Trace TracerProvider for this namespace. Idempotent.
/// pServiceName becomes the service.name OTel resource attribute.
ClassMethod InitProvider(pServiceName As %String = "iris-interop") As %Status
{
    Set tSC = $$$OK
    If ##class(%Trace.Provider).IsDefined() Quit tSC
    Set tAttrs("service.name")    = pServiceName
    Set tAttrs("service.version") = "1.0"
    Set tAttrs("host.name")       = ##class(%SYS.System).GetNodeName()
    Set tProvider = ##class(%Trace.TracerProvider).%New(.tAttrs)
    Set tSC = ##class(%Trace.Provider).SetTracerProvider(tProvider)
    Quit tSC
}

/// Returns 1 if a TracerProvider is registered for this namespace, 0 otherwise.
ClassMethod IsProviderReady() As %Boolean
{
    Quit ##class(%Trace.Provider).IsDefined()
}

}
