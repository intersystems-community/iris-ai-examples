/// SDoH Follow-Up Business Service — entry point from MCP tool call
Class CareConnect.Service.SDoHFollowUpBS Extends Ens.BusinessService
{

Parameter ADAPTER = "";

Method OnProcessInput(pRequest As CareConnect.Message.FollowUpRequest, Output pResponse As CareConnect.Message.FollowUpResponse) As %Status
{
    Quit ..SendRequestSync("CareConnect.Process.SDoHFollowUpBP", pRequest, .pResponse)
}

}
