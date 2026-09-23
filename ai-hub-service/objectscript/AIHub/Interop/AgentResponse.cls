/// The state of an agent run, as AIHub.Interop.AgentOperation last saw it.
Class AIHub.Interop.AgentResponse Extends Ens.Response
{

Property RunId As %String(MAXLEN = 100);

/// running, awaiting_approval, succeeded, failed or cancelled.
Property Status As %String(MAXLEN = 50);

/// The run's answer once it has succeeded.
Property Output As %String(MAXLEN = "");

/// The tool a parked run is waiting on an approver for.
Property AwaitingTool As %String(MAXLEN = 200);

Property Error As %String(MAXLEN = "");

/// Number of tool calls the run made, from its audit trail.
Property StepCount As %Integer;

}
