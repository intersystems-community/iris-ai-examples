/// Business operation that puts AI Hub Service agents inside a production.
///
/// Drop it into any production, on any IRIS version with Interoperability, and
/// point it at the service. A business process then calls an agent the way it
/// calls anything else — send an AgentRequest, get an AgentResponse — and the
/// call is traced in the message viewer with the rest of the flow.
///
///   <Item Name="AIHub.Agents" ClassName="AIHub.Interop.AgentOperation" Enabled="true">
///     <Setting Target="Adapter" Name="HTTPServer">aihub-service</Setting>
///     <Setting Target="Adapter" Name="HTTPPort">8080</Setting>
///     <Setting Target="Adapter" Name="ResponseTimeout">120</Setting>
///     <Setting Target="Host" Name="APIKeyCredentials">aihub-app-key</Setting>
///   </Item>
///
/// The API key is read from an Interoperability credential (its Password field)
/// so it never appears in a production definition or a message.
Class AIHub.Interop.AgentOperation Extends Ens.BusinessOperation
{

Parameter ADAPTER = "EnsLib.HTTP.OutboundAdapter";

Parameter INVOCATION = "Queue";

/// Ens.Config.Credentials entry whose Password is the service API key.
Property APIKeyCredentials As %String(MAXLEN = 200);

Parameter SETTINGS = "APIKeyCredentials:Basic:credentialsSelector";

Method RunAgent(pRequest As AIHub.Interop.AgentRequest, Output pResponse As AIHub.Interop.AgentResponse) As %Status
{
    Set body = ##class(%DynamicObject).%New()
    Do body.%Set("input", pRequest.Input)
    Do body.%Set("wait", ''pRequest.Wait, "boolean")
    If pRequest.ContextJSON '= "" Do body.%Set("context", ##class(%DynamicObject).%FromJSON(pRequest.ContextJSON))
    Set path = "/v1/agents/"_$ZConvert(pRequest.Agent, "O", "URL")_"/runs"
    Set sc = ..Send("POST", path, body, .run)
    Quit:$$$ISERR(sc) sc
    Set pResponse = ..ToResponse(run)
    Quit $$$OK
}

Method RunStatus(pRequest As AIHub.Interop.RunStatusRequest, Output pResponse As AIHub.Interop.AgentResponse) As %Status
{
    Set sc = ..Send("GET", "/v1/runs/"_$ZConvert(pRequest.RunId, "O", "URL"), "", .run)
    Quit:$$$ISERR(sc) sc
    Set pResponse = ..ToResponse(run)
    Quit $$$OK
}

ClassMethod ToResponse(run As %DynamicObject) As AIHub.Interop.AgentResponse
{
    Set resp = ##class(AIHub.Interop.AgentResponse).%New()
    Set resp.RunId = run.id
    Set resp.Status = run.status
    Set resp.Output = run.output
    Set resp.Error = run.error
    Set awaiting = run.%Get("awaiting_approval")
    If $IsObject(awaiting) Set resp.AwaitingTool = awaiting.tool
    If $IsObject(run.steps) Set resp.StepCount = run.steps.%Size()
    Quit resp
}

/// One JSON request through the adapter. The adapter supplies server, port,
/// TLS, timeouts and retry; this adds the key and the JSON body.
Method Send(method As %String, path As %String, body As %DynamicObject, Output run As %DynamicObject) As %Status
{
    Set run = ##class(%DynamicObject).%New()
    Set req = ##class(%Net.HttpRequest).%New()
    Do req.SetHeader("Accept", "application/json")
    Set key = ..APIKey()
    If key '= "" Do req.SetHeader("Authorization", "Bearer "_key)
    If $IsObject(body) {
        Set req.ContentType = "application/json"
        Do body.%ToJSON(req.EntityBody)
    }
    Set sc = ..Adapter.SendFormDataArray(.httpResponse, method, req, , , ..Adapter.URL_path)
    If $IsObject($Get(httpResponse)) && $IsObject(httpResponse.Data) {
        Set text = ""
        Do httpResponse.Data.Rewind()
        While 'httpResponse.Data.AtEnd { Set text = text_httpResponse.Data.Read(32000) }
        If text '= "" {
            Try {
                Set run = ##class(%DynamicAbstractObject).%FromJSON(text)
            } Catch ex {
                Set sc = $System.Status.AppendStatus(sc, ex.AsStatus())
            }
        }
        If $$$ISERR(sc) && $IsObject(run) && (run.detail '= "") {
            Set sc = $System.Status.AppendStatus(sc, $System.Status.Error(5001, "AI Hub Service: "_run.detail))
        }
    }
    Quit sc
}

Method APIKey() As %String
{
    If ..APIKeyCredentials = "" Quit ""
    Set cred = ##class(Ens.Config.Credentials).%OpenId(..APIKeyCredentials)
    If '$IsObject(cred) Quit ""
    Quit cred.Password
}

XData MessageMap
{
<MapItems>
  <MapItem MessageType="AIHub.Interop.AgentRequest">
    <Method>RunAgent</Method>
  </MapItem>
  <MapItem MessageType="AIHub.Interop.RunStatusRequest">
    <Method>RunStatus</Method>
  </MapItem>
</MapItems>
}

}
