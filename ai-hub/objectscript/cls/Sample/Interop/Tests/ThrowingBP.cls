Include %occStatus

/// Stub that throws from OnHandleRequest — tests exception propagation through OnRequest.
Class Sample.Interop.Tests.ThrowingBP Extends Sample.Interop.Tests.StubBP
{

Method OnHandleRequest(pRequest As %RegisteredObject, Output pResponse As %RegisteredObject) As %Status
{
    Throw ##class(%Exception.General).%New("TestError", "5001", , "intentional throw")
}

}
