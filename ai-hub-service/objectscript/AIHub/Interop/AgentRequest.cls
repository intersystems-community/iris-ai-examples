/// Ask AI Hub Service to run an agent. Send to AIHub.Interop.AgentOperation.
Class AIHub.Interop.AgentRequest Extends Ens.Request
{

/// Agent name, as GET /v1/agents lists it.
Property Agent As %String(MAXLEN = 200) [ Required ];

/// Free-text instruction. Playbook agents may need only ContextJSON.
Property Input As %String(MAXLEN = "");

/// JSON object: the run's context, e.g. {"patientId":"maria-gonzalez-001"}.
Property ContextJSON As %String(MAXLEN = "");

/// 1: wait for the run to settle. 0: return at once with the run id, and
/// poll with an AIHub.Interop.RunStatusRequest.
Property Wait As %Boolean [ InitialExpression = 1 ];

}
