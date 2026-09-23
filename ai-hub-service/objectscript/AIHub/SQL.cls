/// Agents from SQL. For applications whose logic lives in queries, reports and
/// stored procedures: an agent run is one scalar function call.
///
///   SELECT AIHub.Ask('sdoh-assessment', '', '{"patientId":"maria-gonzalez-001"}')
///
///   SELECT PatientId, AIHub.Ask('sdoh-assessment', '', '{"patientId":"'||PatientId||'"}')
///   FROM CareConnect.Patient
///
///   SELECT AIHub.Tool('AssessSDoHRisk', '{"patientId":"p1","clinicalSummary":"lives alone"}')
///
/// Connection settings come from AIHub.Client.Configure(). Each call is one
/// HTTP round trip that waits for the run, so a function over many rows is a
/// batch job, not an interactive query — the design doc says what to use instead.
Class AIHub.SQL [ Abstract ]
{

/// Run <var>agent</var> and return its output, or a line beginning ERROR: or
/// AWAITING_APPROVAL <runId>: when it did not finish.
ClassMethod Ask(agent As %String, input As %String = "", contextJSON As %String = "") As %String(MAXLEN = "") [ SqlName = Ask, SqlProc ]
{
    Quit ##class(AIHub.Client).FromConfig().Ask(agent, input, contextJSON)
}

/// Call one tool directly and return its text output (or ERROR: ...).
ClassMethod Tool(tool As %String, argsJSON As %String = "{}") As %String(MAXLEN = "") [ SqlName = Tool, SqlProc ]
{
    Set args = ""
    Try {
        Set args = ##class(%DynamicObject).%FromJSON($Select(argsJSON = "": "{}", 1: argsJSON))
    } Catch {
        Quit
    }
    If '$IsObject(args) Quit "ERROR: argsJSON is not valid JSON"
    Set sc = ##class(AIHub.Client).FromConfig().InvokeTool(tool, args, .result)
    If $$$ISERR(sc) Quit "ERROR: "_$System.Status.GetErrorText(sc)
    Quit result.output
}

/// A run's status: succeeded, failed, cancelled, running or awaiting_approval.
ClassMethod RunStatus(runId As %String) As %String [ SqlName = RunStatus, SqlProc ]
{
    Set sc = ##class(AIHub.Client).FromConfig().GetRun(runId, .run)
    If $$$ISERR(sc) Quit "ERROR: "_$System.Status.GetErrorText(sc)
    Quit run.status
}

/// A run's output once it has settled; the same text Ask() returns.
ClassMethod RunOutput(runId As %String) As %String(MAXLEN = "") [ SqlName = RunOutput, SqlProc ]
{
    Set sc = ##class(AIHub.Client).FromConfig().GetRun(runId, .run)
    If $$$ISERR(sc) Quit "ERROR: "_$System.Status.GetErrorText(sc)
    Quit ##class(AIHub.Client).Describe(run)
}

}
