/// ObjectScript client for AI Hub Service. The one class an IRIS application
/// needs in order to use agents: no SDK, no %AI, no model credentials, and no
/// particular IRIS version — %Net.HttpRequest and %DynamicObject are all it uses.
///
/// Configure once per namespace (the key belongs in a secret store in production):
///
///   Do ##class(AIHub.Client).Configure("aihub-service", 8080, "dev-app-key")
///
/// Then, from any routine, class, or business host:
///
///   Set client = ##class(AIHub.Client).FromConfig()
///   Set ctx = {"patientId": "maria-gonzalez-001"}
///   Set sc = client.RunAgent("sdoh-assessment", "", ctx, 1, .run)
///   Write run.status, !, run.output, !
///
/// A run that reaches a gated tool comes back with status "awaiting_approval";
/// an approver resumes it with Decide(). SQL callers use AIHub.SQL; productions
/// use AIHub.Interop.AgentOperation. Both sit on this class.
Class AIHub.Client Extends %RegisteredObject
{

Property Server As %String [ InitialExpression = "aihub-service" ];

Property Port As %Integer [ InitialExpression = 8080 ];

/// Non-empty means HTTPS, using this SSL/TLS configuration.
Property SSLConfiguration As %String;

Property APIKey As %String(MAXLEN = 500);

/// Seconds. A waited-for run holds the connection for the whole run.
Property Timeout As %Integer [ InitialExpression = 120 ];

/// Store the connection settings for this namespace in ^AIHub.Config("client").
ClassMethod Configure(server As %String, port As %Integer = 8080, apiKey As %String = "", sslConfiguration As %String = "", timeout As %Integer = 120) As %Status
{
    Set ^AIHub.Config("client", "server") = server
    Set ^AIHub.Config("client", "port") = port
    Set ^AIHub.Config("client", "key") = apiKey
    Set ^AIHub.Config("client", "ssl") = sslConfiguration
    Set ^AIHub.Config("client", "timeout") = timeout
    Quit $$$OK
}

/// A client built from the settings Configure() stored.
ClassMethod FromConfig() As AIHub.Client
{
    Set client = ..%New()
    Set client.Server = $Get(^AIHub.Config("client", "server"), client.Server)
    Set client.Port = $Get(^AIHub.Config("client", "port"), client.Port)
    Set client.APIKey = $Get(^AIHub.Config("client", "key"))
    Set client.SSLConfiguration = $Get(^AIHub.Config("client", "ssl"))
    Set client.Timeout = $Get(^AIHub.Config("client", "timeout"), client.Timeout)
    Quit client
}

/// Start a run of <var>agent</var>. With <var>wait</var> the call returns when the run
/// succeeds, fails, or parks for approval; without it, at once, to be polled with GetRun().
Method RunAgent(agent As %String, input As %String = "", context As %DynamicObject = "", wait As %Boolean = 1, Output run As %DynamicObject) As %Status
{
    Set body = ##class(%DynamicObject).%New()
    Do body.%Set("input", input)
    Do body.%Set("wait", ''wait, "boolean")
    If $IsObject(context) Do body.%Set("context", context)
    Quit ..Call("POST", "/v1/agents/"_..Segment(agent)_"/runs", body, .run)
}

Method GetRun(runId As %String, Output run As %DynamicObject) As %Status
{
    Quit ..Call("GET", "/v1/runs/"_..Segment(runId), "", .run)
}

/// Approve or reject the gated call a run is waiting on. Needs an approver's key.
Method Decide(runId As %String, approve As %Boolean, reason As %String = "", Output run As %DynamicObject) As %Status
{
    Set body = ##class(%DynamicObject).%New()
    Do body.%Set("decision", $Select(approve: "approve", 1: "reject"))
    Do body.%Set("reason", reason)
    Quit ..Call("POST", "/v1/runs/"_..Segment(runId)_"/approval", body, .run)
}

/// Runs waiting on a human decision. Approvers see everyone's.
Method AwaitingApproval(Output runs As %DynamicObject) As %Status
{
    Quit ..Call("GET", "/v1/runs?status=awaiting_approval", "", .runs)
}

/// Call one tool directly: no agent, no model.
Method InvokeTool(tool As %String, args As %DynamicObject = "", Output result As %DynamicObject) As %Status
{
    Set body = ##class(%DynamicObject).%New()
    Do body.%Set("args", $Select($IsObject(args): args, 1: ##class(%DynamicObject).%New()))
    Quit ..Call("POST", "/v1/tools/"_..Segment(tool)_"/invoke", body, .result)
}

/// One-line convenience for callers that want text: the run's output, or a
/// line starting ERROR: or AWAITING_APPROVAL that says what happened instead.
Method Ask(agent As %String, input As %String = "", contextJSON As %String = "") As %String
{
    Set context = ""
    Try {
        If contextJSON '= "" Set context = ##class(%DynamicObject).%FromJSON(contextJSON)
    } Catch {
        Quit
    }
    If (contextJSON '= "") && '$IsObject(context) Quit "ERROR: contextJSON is not valid JSON"
    Set sc = ..RunAgent(agent, input, context, 1, .run)
    If $$$ISERR(sc) Quit "ERROR: "_$System.Status.GetErrorText(sc)
    Quit ..Describe(run)
}

/// Render a run as the text Ask() returns.
ClassMethod Describe(run As %DynamicObject) As %String
{
    If run.status = "succeeded" Quit run.output
    If run.status = "awaiting_approval" Quit "AWAITING_APPROVAL "_run.id_": "_run.%Get("awaiting_approval").%Get("tool")_" needs an approver"
    Quit "ERROR: run "_run.id_" "_run.status_$Select(run.error '= "": ": "_run.error, 1: "")
}

/// Send one request and parse the JSON reply. An HTTP error status becomes an
/// error %Status carrying the service's own "detail" message.
Method Call(method As %String, path As %String, body As %DynamicObject = "", Output response As %DynamicObject) As %Status
{
    Set sc = $$$OK
    Set response = ##class(%DynamicObject).%New()
    Try {
        Set req = ##class(%Net.HttpRequest).%New()
        Set req.Server = ..Server
        Set req.Port = ..Port
        Set req.Timeout = ..Timeout
        If ..SSLConfiguration '= "" {
            Set req.Https = 1
            Set req.SSLConfiguration = ..SSLConfiguration
        }
        Do req.SetHeader("Authorization", "Bearer "_..APIKey)
        Do req.SetHeader("Accept", "application/json")
        If $IsObject(body) {
            Set req.ContentType = "application/json"
            Do body.%ToJSON(req.EntityBody)
        }
        Set sc = req.Send(method, path)
        If $$$ISERR(sc) Quit
        Set resp = req.HttpResponse
        Set text = ""
        If $IsObject(resp.Data) {
            While 'resp.Data.AtEnd { Set text = text_resp.Data.Read(32000) }
        } Else {
            Set text = resp.Data
        }
        If text '= "" Set response = ##class(%DynamicAbstractObject).%FromJSON(text)
        If resp.StatusCode >= 400 {
            Set detail = response.detail
            If $IsObject(detail) Set detail = detail.%ToJSON()
            Set sc = $System.Status.Error(5001, "AI Hub Service HTTP "_resp.StatusCode_": "_detail)
        }
    } Catch ex {
        Set sc = ex.AsStatus()
    }
    Quit sc
}

ClassMethod Segment(value As %String) As %String [ CodeMode = expression ]
{
$ZConvert(value, "O", "URL")
}

}
