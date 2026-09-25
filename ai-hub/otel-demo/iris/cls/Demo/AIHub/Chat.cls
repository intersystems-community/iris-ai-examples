Include (%AI, %occStatus)

/// Entry points the demo web app calls over the native API.
///
/// Ask runs one %AI.Agent turn. The caller's traceparent goes to the Rust layer
/// through telemetry:context, so invoke_agent, chat and execute_tool nest under
/// the app's span, and the interop spans the tool causes nest under execute_tool.
/// Agents and sessions live in %AIHubChat for the life of the connection's process.
Class Demo.AIHub.Chat Extends %RegisteredObject
{

/// Low enough that small local models call the tool reliably instead of drifting.
Parameter TEMPERATURE = 0.2;

Parameter SYSTEMPROMPT = "You are a clinical assistant. Use the LookupPatient tool for any question about a patient. Answer in two sentences or fewer.";

/// Returns {"content":..., "error":...} as JSON text.
ClassMethod Ask(pSessionId As %String, pQuestion As %String, pTraceparent As %String = "") As %String
{
    Set tOut = {"content":"", "error":""}
    Try {
        $$$ThrowOnError(..EnsureReady())
        Set tCtx = {"session_id":(pSessionId)}
        If pTraceparent '= "" { Set tCtx.traceparent = pTraceparent }
        $$$ThrowOnError(##class(%AI.System).Configure("telemetry:context", tCtx))
        If '$IsObject($Get(%AIHubChat(pSessionId, "agent"))) {
            $$$ThrowOnError(..NewAgent(pSessionId))
        }
        Set tAgent = %AIHubChat(pSessionId, "agent")
        Set tResp = tAgent.Chat(%AIHubChat(pSessionId, "session"), pQuestion)
        Set tOut.content = tResp.Content
    } Catch tEx {
        Set tOut.error = tEx.DisplayString()
    }
    Do ##class(%AI.System).Configure("telemetry:context", {})
    Quit tOut.%ToJSON()
}

/// The LangChain tab's tool: the same interop lookup, parented on pTraceparent.
ClassMethod Lookup(pPatientId As %String, pTraceparent As %String = "") As %String
{
    Set tSC = ..EnsureReady()
    If $$$ISERR(tSC) Quit "{""error"": """_$ZConvert($System.Status.GetErrorText(tSC), "O", "JSON")_"""}"
    Quit ##class(Demo.AIHub.PatientTools).Interop(pPatientId, pTraceparent)
}

/// Tracer provider registered and the production running. Idempotent.
ClassMethod EnsureReady() As %Status
{
    Set tSC = $$$OK
    Set tSC = ##class(Sample.Interop.OTelSetup).InitProvider("aihub-otel-demo")
    If $$$ISERR(tSC) Quit tSC
    If '##class(Ens.Director).IsProductionRunning(.tName) || (tName '= "Demo.AIHub.Production") {
        // StartProduction writes progress to the current device. Under the native
        // API that device is the protocol socket, and stray bytes desync it.
        Set tIO = $IO
        Open "/dev/null":"W":1
        Use "/dev/null"
        Try {
            Set tSC = ##class(Ens.Director).StartProduction("Demo.AIHub.Production")
        } Catch tEx {
            Set tSC = tEx.AsStatus()
        }
        Use tIO
        Close "/dev/null"
    }
    Quit tSC
}

/// DEMO_MODEL and DEMO_LLM_BASE_URL mirror the app's settings (demo_app/llm_config.py):
/// unset, OpenAI gpt-4o-mini; set, any OpenAI-compatible server such as Ollama.
ClassMethod NewAgent(pSessionId As %String) As %Status [ Private ]
{
    Set tSC = $$$OK
    Set tSettings = {"api_key":($System.Util.GetEnviron("OPENAI_API_KEY"))}
    If tSettings."api_key" = "" { Set tSettings."api_key" = "unused" }
    Set tBaseUrl = $System.Util.GetEnviron("DEMO_LLM_BASE_URL")
    If tBaseUrl '= "" { Set tSettings."base_url" = tBaseUrl }
    Set tModel = $System.Util.GetEnviron("DEMO_MODEL")
    Set tProvider = ##class(%AI.Provider).Create("openai", tSettings)
    Set tAgent = ##class(%AI.Agent).%New(tProvider)
    Set tAgent.Model = $Select(tModel '= "": tModel, 1: "gpt-4o-mini")
    Set tAgent.SystemPrompt = ..#SYSTEMPROMPT
    Set tAgent.Temperature = ..#TEMPERATURE
    Set tSC = tAgent.ToolManager.AddTool(##class(Demo.AIHub.PatientTools).%New())
    If $$$ISERR(tSC) Quit tSC
    Set %AIHubChat(pSessionId, "agent") = tAgent
    Set %AIHubChat(pSessionId, "session") = tAgent.CreateSession(##class(%AI.Shell.Console).InitializeConfig(tProvider))
    Quit tSC
}

}
