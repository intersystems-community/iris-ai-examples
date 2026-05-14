/// SDoH Follow-Up request message
Class CareConnect.Message.FollowUpRequest Extends Ens.Request
{

Property PatientId As %String;
Property Priority  As %String [ InitialExpression = "routine" ];
Property SDoHFlags As %String(MAXLEN = 2000);

}
