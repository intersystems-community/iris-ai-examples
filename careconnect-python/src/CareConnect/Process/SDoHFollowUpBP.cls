/// SDoH Follow-Up Business Process — orchestrates the care coordination workflow
Class CareConnect.Process.SDoHFollowUpBP Extends Ens.BusinessProcess [ ClassType = persistent ]
{

Method OnRequest(pRequest As CareConnect.Message.FollowUpRequest, Output pResponse As CareConnect.Message.FollowUpResponse) As %Status
{
    Set pResponse = ##class(CareConnect.Message.FollowUpResponse).%New()
    Set pResponse.JobId = $SYSTEM.Util.CreateGUID()
    Set pResponse.Status = "accepted"
    Set sc = ..SendRequestAsync("CareConnect.Operation.SDoHFollowUpBO", pRequest)
    If $$$ISERR(sc) {
        Set pResponse.Status = "error"
        Set pResponse.Error = $System.Status.GetErrorText(sc)
    }
    Quit $$$OK
}

Method OnResponse(pRequest As Ens.Request, pResponse As Ens.Response, pCallRequest As Ens.Request, pCallResponse As Ens.Response, pCompletionKey As %String) As %Status
{
    Quit $$$OK
}

Storage Default
{
<Type>%Storage.Persistent</Type>
}

}
