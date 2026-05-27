/// SDoH Follow-Up Business Operation — logs the follow-up action
Class CareConnect.Operation.SDoHFollowUpBO Extends Ens.BusinessOperation
{

Parameter ADAPTER = "Ens.OutboundAdapter";
Parameter INVOCATION = "Queue";

Method FollowUp(pRequest As CareConnect.Message.FollowUpRequest, Output pResponse As CareConnect.Message.FollowUpResponse) As %Status
{
    Set pResponse = ##class(CareConnect.Message.FollowUpResponse).%New()
    Set pResponse.JobId = $SYSTEM.Util.CreateGUID()
    Set pResponse.Status = "completed"
    $$$LOGINFO("SDoH follow-up processed — patient: "_pRequest.PatientId_" priority: "_pRequest.Priority)
    Quit $$$OK
}

XData MessageMap
{
<MapItems>
  <MapItem MessageType="CareConnect.Message.FollowUpRequest">
    <Method>FollowUp</Method>
  </MapItem>
</MapItems>
}

}
