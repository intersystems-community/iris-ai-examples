/// Poll a run started with Wait = 0. Answered with an AIHub.Interop.AgentResponse.
Class AIHub.Interop.RunStatusRequest Extends Ens.Request
{

Property RunId As %String(MAXLEN = 100) [ Required ];

}
