Include (%AI, %occStatus)

/// Bridge agent for the Python @tool + iris_tool_bridge pattern.
///
/// Phase 6 note: RunQueryWithStats emits OTel spans (gen_ai.* semantic conventions)
/// via Bridge.AuditPolicy.  The audit policy is attached before %Init() so all
/// tool-call spans become children of the pre-generated chat span (W3C traceparent
/// propagation).  The returned DynamicObject includes trace_id and span_id so the
/// Python caller can stitch its own spans into the same trace.
///
/// Provides a governed entry point for Python-defined toolsets: the provider
/// is resolved from a named ConfigStore entry (AI.LLM.*) so credentials,
/// model selection, and access control go through IRIS RBAC — not hardcoded
/// environment variables.
///
/// Usage from Python (irispython / embedded):
///
///   result = iris.cls('Sample.AI.Bridge.Agent').RunQuery(
///       'AI.LLM.SampleOpenAI',          # ConfigStore config FQN
///       'Tmp.Bridge.IRISInfoToolsToolSet', # compiled bridge ToolSet class
///       'What namespaces exist in this IRIS instance?'
///   )
///   print(result)
///
/// Usage from ObjectScript:
///   Set tResult = ##class(Sample.AI.Bridge.Agent).RunQuery(
///       "AI.LLM.SampleOpenAI",
///       "Tmp.Bridge.IRISInfoToolsToolSet",
///       "What namespaces exist?")
///   Write tResult
///
/// The ConfigStore entry must be an AI.LLM descriptor with at least:
///   { "model_provider": "openai", "model": "gpt-4o-mini",
///     "api_key": "@{env:OPENAI_API_KEY}" }
///
/// Create one with:
///   Do ##class(Sample.AI.Examples.ConfigStoreSetup).Run()
Class Sample.AI.Bridge.Agent Extends %RegisteredObject
{

/// Run a single query using a ConfigStore-governed provider and a Python bridge ToolSet.
///
/// pConfigName  — ConfigStore FQN, e.g. "AI.LLM.SampleOpenAI"
/// pToolSetClass — compiled %AI.ToolSet class name (from iris_tool_bridge)
/// pQuery        — natural-language query
///
/// Returns the agent response text, or an error description on failure.
ClassMethod RunQuery(
    pConfigName  As %String,
    pToolSetClass As %String,
    pQuery        As %String) As %String
{
    Set tSC = $$$OK
    Try {
        // 1. Prime the SettingStore so @{config:...} / @{env:...} resolve
        Set tSC = ##class(%AI.Utils.SettingStore).RegisterDefaults()
        If $$$ISERR(tSC) {
            Return "Error registering SettingStore: " _ $System.Status.GetErrorText(tSC)
        }

        // 2. Verify the config exists before expanding
        If '##class(%ConfigStore.Configuration).Exists(pConfigName) {
            Return "ConfigStore entry not found: " _ pConfigName
                _ " — run ##class(Sample.AI.Examples.ConfigStoreSetup).Run() first."
        }

        // 3. Expand the config placeholder to a JSON settings object
        Set tPlaceholder = "@{config:" _ pConfigName _ "}"
        Set tSettingsJson = ##class(%AI.Utils.SettingStore).Expand(tPlaceholder)
        Set tSettings = {}.%FromJSON(tSettingsJson)

        // 4. Determine provider name from settings
        Set tProviderName = tSettings.%Get("model_provider")
        If tProviderName = "" {
            Return "Config '" _ pConfigName _ "' missing model_provider field."
        }

        // 5. Create the governed provider — RBAC is enforced by ConfigStore.UseConfiguration
        //    which fires inside SettingStore.Expand above.
        Set tProvider = ##class(%AI.Provider).Create(tProviderName, tSettings)

        // 6. Build agent with the resolved provider already set.
        //    %Init() will skip %CreateProvider() since Provider is already set,
        //    then registers SettingStore defaults (idempotent) and loads instructions.
        Set tAgent = ##class(%AI.Agent).%New(tProvider)
        Set tModel = tSettings.%Get("model")
        If tModel '= "" {
            Set tAgent.Model = tModel
        }
        Set tAgent.SystemPrompt =
            "You are an IRIS database assistant. Use the available tools to answer "
            _ "questions with live data from this IRIS instance. Be concise."

        // 7. Load the bridge ToolSet (compiled ObjectScript class from iris_tool_bridge)
        If pToolSetClass '= "" {
            If '##class(%Dictionary.CompiledClass).%ExistsId(pToolSetClass) {
                Return "ToolSet class not found: " _ pToolSetClass
                    _ " — run bridge registration first."
            }
            Do tAgent.ToolManager.AddTool($CLASSMETHOD(pToolSetClass, "%New"))
        }

        // 8. %Init() to finalize (loads instructions, skips provider creation)
        Set tSC = tAgent.%Init()
        If $$$ISERR(tSC) {
            Return "Agent init error: " _ $System.Status.GetErrorText(tSC)
        }

        // 9. Run the query
        Set tSession = tAgent.CreateSession()
        Set tResponse = tAgent.Chat(tSession, pQuery)

        If '$IsObject(tResponse) {
            Return "No response returned."
        }
        Return tResponse.Content

    } Catch ex {
        Return "Error: " _ ex.DisplayString()
    }
}

/// Return a %DynamicObject with response content, token usage, and OTel trace IDs.
///
/// OTel: attaches a Bridge.AuditPolicy before %Init() so every tool-call span
/// is emitted as a child of the pre-generated chat span.  Returns trace_id and
/// span_id so the Python caller can stitch its own OTel spans into the same trace.
///
/// OTel is active when OTEL_EXPORTER_OTLP_ENDPOINT is set in the IRIS process env.
/// All OTEL_* vars are read by Bridge.AuditPolicy at %New() time.
///
/// Result keys:
///   content          — agent response text
///   prompt_tokens    — LLM input token count
///   completion_tokens— LLM output token count
///   error            — non-empty on failure
///   trace_id         — 32-hex OTel trace ID (empty when OTel disabled)
///   span_id          — 16-hex chat span ID  (empty when OTel disabled)
ClassMethod RunQueryWithStats(
    pConfigName   As %String,
    pToolSetClass As %String,
    pQuery        As %String) As %DynamicObject
{
    Set tSC = $$$OK
    Set tResult = {"content": "", "prompt_tokens": 0, "completion_tokens": 0,
                   "error": "", "trace_id": "", "span_id": ""}
    Try {
        Set tSC = ##class(%AI.Utils.SettingStore).RegisterDefaults()
        If $$$ISERR(tSC) {
            Do tResult.%Set("error", $System.Status.GetErrorText(tSC))
            Return tResult
        }

        If '##class(%ConfigStore.Configuration).Exists(pConfigName) {
            Do tResult.%Set("error", "ConfigStore entry not found: " _ pConfigName)
            Return tResult
        }

        Set tPlaceholder = "@{config:" _ pConfigName _ "}"
        Set tSettingsJson = ##class(%AI.Utils.SettingStore).Expand(tPlaceholder)
        Set tSettings = {}.%FromJSON(tSettingsJson)

        Set tProviderName = tSettings.%Get("model_provider")
        If tProviderName = "" {
            Do tResult.%Set("error", "Config missing model_provider: " _ pConfigName)
            Return tResult
        }

        Set tProvider = ##class(%AI.Provider).Create(tProviderName, tSettings)
        Set tAgent = ##class(%AI.Agent).%New(tProvider)
        Set tModel = tSettings.%Get("model")
        If tModel '= "" { Set tAgent.Model = tModel }
        Set tAgent.SystemPrompt =
            "You are an IRIS database assistant. Use tools to answer with live data. Be concise."

        If pToolSetClass '= "" {
            If ##class(%Dictionary.CompiledClass).%ExistsId(pToolSetClass) {
                Do tAgent.ToolManager.AddTool($CLASSMETHOD(pToolSetClass, "%New"))
            }
        }

        // OTel setup — pre-generate IDs so tool spans can reference the chat span as parent
        Set tOtelEnabled = ($System.Util.GetEnviron("OTEL_EXPORTER_OTLP_ENDPOINT") '= "")
        Set tAuditPolicy = ##class(Sample.AI.Bridge.AuditPolicy).%New()
        Set tTraceId = ""
        Set tChatSpanId = ""
        If tOtelEnabled {
            Set tTraceId    = ##class(Sample.AI.Policies.OTelAuditPolicy).GenHexId(32)
            Set tChatSpanId = ##class(Sample.AI.Policies.OTelAuditPolicy).GenHexId(16)
            // Set traceparent so tool-call spans emitted by audit policy wire as children
            Set tAuditPolicy.Traceparent = "00-" _ tTraceId _ "-" _ tChatSpanId _ "-01"
            Do tResult.%Set("trace_id", tTraceId)
            Do tResult.%Set("span_id",  tChatSpanId)
        }
        Set tAgent.AuditPolicy = tAuditPolicy

        Set tSC = tAgent.%Init()
        If $$$ISERR(tSC) {
            Do tResult.%Set("error", $System.Status.GetErrorText(tSC))
            Return tResult
        }

        Set tPromptTok = 0
        Set tCompTok   = 0
        Set tSession = tAgent.CreateSession()
        Set tStartNs = tAuditPolicy.NowNs()
        Set tResponse = tAgent.Chat(tSession, pQuery)
        Set tEndNs   = tAuditPolicy.NowNs()

        If $IsObject(tResponse) {
            Do tResult.%Set("content", tResponse.Content)
            If $IsObject(tResponse.Usage) {
                Set tPromptTok = +tResponse.Usage.%Get("prompt_tokens")
                Set tCompTok   = +tResponse.Usage.%Get("completion_tokens")
                Do tResult.%Set("prompt_tokens",     tPromptTok)
                Do tResult.%Set("completion_tokens", tCompTok)
            }
        }

        // Emit the chat span after Chat() returns — tool spans already emitted as children
        If tOtelEnabled {
            Set tStartStr = tStartNs _ ""
            Set tEndStr   = tEndNs _ ""
            Set tContent  = ""
            If $IsObject(tResponse) { Set tContent = $Extract(tResponse.Content, 1, 200) }
            Set tAttrs = [
                {"key": "gen_ai.operation.name",   "value": {"stringValue": "chat"}},
                {"key": "gen_ai.system",            "value": {"stringValue": "iris"}},
                {"key": "gen_ai.request.model",     "value": {"stringValue": (tModel)}},
                {"key": "gen_ai.usage.input_tokens","value": {"intValue": (tPromptTok)}},
                {"key": "gen_ai.usage.output_tokens","value":{"intValue": (tCompTok)}},
                {"key": "gen_ai.config_name",       "value": {"stringValue": (pConfigName)}}
            ]
            Set tSpanObj = {
                "traceId":  (tTraceId),
                "spanId":   (tChatSpanId),
                "name":     "chat",
                "kind":     3,
                "startTimeUnixNano": (tStartStr),
                "endTimeUnixNano":   (tEndStr),
                "attributes": (tAttrs),
                "status": {"code": 1}
            }
            Do tAuditPolicy.PostOtlp(tSpanObj)
        }

    } Catch ex {
        Do tResult.%Set("error", ex.DisplayString())
    }
    Return tResult
}

}
