Include (%AI, %occStatus)

/// OTel LLM Observability Example
/// Demonstrates end-to-end OpenTelemetry span emission for AI agent calls.
///
/// Prerequisites:
///   Set $System.Util.SetEnviron("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318/v1/traces")
///   Set $System.Util.SetEnviron("OTEL_SERVICE_NAME", "iris-ai-agent")
///   Set $System.Util.SetEnviron("ANTHROPIC_API_KEY", "<key>")  // or OPENAI_API_KEY
///
/// This emits two spans per Chat() call:
///   gen_ai.chat  — LLM call duration + token counts (from OTelAgent)
///     └── tool_call/ListTools — each tool invocation (from OTelAuditPolicy)
///
/// Run from terminal:  Do ##class(Sample.AI.Examples.OTelObservability).Run()
Class Sample.AI.Examples.OTelObservability Extends %RegisteredObject
{

/// Run a single-turn agent conversation with full OTel tracing.
/// Spans are sent to OTEL_EXPORTER_OTLP_ENDPOINT (default: localhost:4318).
ClassMethod Run() As %Status
{
    Set tSC = $$$OK
    Try {
        Write !, "=== OTel Observability Example ===", !

        // 1. Configure the LLM provider
        Set tApiKey = $System.Util.GetEnviron("ANTHROPIC_API_KEY")
        If tApiKey = "" { Set tApiKey = $System.Util.GetEnviron("OPENAI_API_KEY") }
        If tApiKey = "" {
            Write "Error: Set ANTHROPIC_API_KEY or OPENAI_API_KEY", !
            Return $$$ERROR($$$GeneralError, "Missing API key")
        }

        Set tProvider = ""
        If $System.Util.GetEnviron("ANTHROPIC_API_KEY") '= "" {
            Set tSettings = {}
            Do tSettings.%Set("api_key", $System.Util.GetEnviron("ANTHROPIC_API_KEY"))
            Set tProvider = ##class(%AI.Provider).Create("anthropic", tSettings)
            Write "Provider: Anthropic", !
        } Else {
            Set tSettings = {}
            Do tSettings.%Set("api_key", $System.Util.GetEnviron("OPENAI_API_KEY"))
            Set tProvider = ##class(%AI.Provider).Create("openai", tSettings)
            Write "Provider: OpenAI", !
        }

        // 2. Create OTelAgent — wraps each Chat() in a gen_ai.chat span
        Set tAgent = ##class(Sample.AI.OTelAgent).%New(tProvider)
        Set tAgent.SystemPrompt = "You are a helpful assistant."

        Write "OTel endpoint: ", tAgent.OTelPolicy.OtlpEndpoint, !
        Write "Service name: ",  tAgent.OTelPolicy.ServiceName, !

        // 3. Optional: propagate an incoming trace context.
        // From a REST endpoint: Do tAgent.OTelPolicy.ExtractTraceparent(%request)
        // From an Interop production: Set tAgent.OTelPolicy.Traceparent = tTraceparentFromMessage

        // 4. Optional: enable prompt/completion capture (off by default — PII guard)
        // Set $System.Util.SetEnviron("OTEL_CAPTURE_CONTENT", "true")

        // 5. Run a conversation
        Set tSession = tAgent.CreateSession()

        Write !, "Sending query...", !
        Set tQuery    = "What is 2 + 2? Answer in one sentence."
        Set tResponse = tAgent.Chat(tSession, tQuery)

        Write "Response: ", tResponse.Content, !

        // 6. Report what was emitted
        Write !, "--- OTel spans emitted ---", !
        Write "  gen_ai.chat span (from OTelAgent.Chat)", !
        If $IsObject(tResponse.Usage) {
            Write "    gen_ai.usage.input_tokens  = ", +tResponse.Usage.%Get("prompt_tokens"), !
            Write "    gen_ai.usage.output_tokens = ", +tResponse.Usage.%Get("completion_tokens"), !
        }
        Write "  Traceparent for next tool call: ", tAgent.OTelPolicy.Traceparent, !
        Write !, "Spans delivered to: ", tAgent.OTelPolicy.OtlpEndpoint, !

    } Catch ex {
        Set tSC = ex.AsStatus()
        Write "Error: ", $System.Status.GetErrorText(tSC), !
    }

    Return tSC
}

/// Demonstrate traceparent propagation: simulate an inbound trace context
/// (as would arrive from an Interop production or external HTTP caller).
ClassMethod RunWithPropagation(traceparent As %String = "") As %Status
{
    Set tSC = $$$OK
    Try {
        Write !, "=== OTel Traceparent Propagation Example ===", !

        If traceparent = "" {
            Set traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
            Write "Using sample traceparent: ", traceparent, !
        }

        // With a real provider (skip in unit testing with no key)
        Set tApiKey = $System.Util.GetEnviron("ANTHROPIC_API_KEY")
        If tApiKey = "" {
            Write "Skipped: no ANTHROPIC_API_KEY (set it to run with a live provider)", !
            Return $$$OK
        }

        Set tSettings = {}
        Do tSettings.%Set("api_key", tApiKey)
        Set tProvider = ##class(%AI.Provider).Create("anthropic", tSettings)

        Set tAgent = ##class(Sample.AI.OTelAgent).%New(tProvider)

        // Inject parent trace — all spans from this agent become children of it.
        // In a real REST handler use: Do tAgent.OTelPolicy.ExtractTraceparent(%request)
        // Here we set it directly since we're not inside a CSP request.
        Set tAgent.OTelPolicy.Traceparent = traceparent
        Write "Parent traceparent set. All spans will use traceId: ", $ListGet($ListFromString(traceparent, "-"), 2), !

        Set tSession  = tAgent.CreateSession()
        Set tResponse = tAgent.Chat(tSession, "Explain what tracing is in one sentence.")
        Write "Response: ", tResponse.Content, !
        Write "Chat span traceparent: ", tAgent.OTelPolicy.Traceparent, !

    } Catch ex {
        Set tSC = ex.AsStatus()
        Write "Error: ", $System.Status.GetErrorText(tSC), !
    }

    Return tSC
}

}
