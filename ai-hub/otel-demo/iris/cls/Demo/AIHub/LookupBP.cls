Include %occStatus

/// BP that forwards the lookup to the BO, carrying its span context in the message.
Class Demo.AIHub.LookupBP Extends Sample.Interop.OTelBusinessProcess
{

/// The base class reads the parent from ^IRIS.Temp.MsgTraceparent($Job), which is
/// per-process; seed it from the persisted message property for this job.
Method OnRequest(pRequest As %Persistent, Output pResponse As %Persistent) As %Status
{
    Set tSC = $$$OK
    If $IsObject(pRequest) && (pRequest.Traceparent '= "") {
        Set ^IRIS.Temp.MsgTraceparent($Job) = pRequest.Traceparent
    }
    Set tSC = ##super(pRequest, .pResponse)
    Kill ^IRIS.Temp.MsgTraceparent($Job)
    Quit tSC
}

Method OnHandleRequest(pRequest As %Persistent, Output pResponse As %Persistent) As %Status
{
    Set tSC = $$$OK
    Set tReq = ##class(Demo.AIHub.PatientRequest).%New()
    Set tReq.PatientId = pRequest.PatientId
    Set tReq.Traceparent = ..TraceparentOut
    Set tSC = ..SendRequestSync("LookupBO", tReq, .pResponse)
    Quit tSC
}

}
