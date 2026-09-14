Include %occStatus

/// Stub Business Operation for CareConnectTrace example.
/// Extends OTelBusinessOperation — OnMessage is automatically instrumented.
/// Override OnProcessMessage (not OnMessage) for outbound logic.
Class Sample.Interop.Examples.CareConnectBO Extends Sample.Interop.OTelBusinessOperation
{

Method OnProcessMessage(pRequest As %Library.Persistent, Output pResponse As %Library.Persistent) As %Status
{
    Set pResponse = ##class(%DynamicObject).%New()
    Quit $$$OK
}

}
