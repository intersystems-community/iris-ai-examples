Include (%AI, %occStatus)

/// %AI.Agent subclass that emits gen_ai.chat spans with token counts for each LLM call.
///
/// Usage:
///   Set agent = ##class(Sample.AI.OTelAgent).%New()
///   // Optional: inject an inbound traceparent (e.g. from a REST caller)
///   Do agent.OTelPolicy.ExtractTraceparent(%request)
///   Set session = agent.CreateSession()
///   Set response = agent.Chat(session, "What tools do you have?")
///   // gen_ai.chat span emitted; agent.OTelPolicy.Traceparent updated
///   // Subsequent tool-call spans (from policies) become children of that chat span
///
/// For tool-call spans, attach OTelAuditPolicy to the ToolSet:
///   <Policies><Audit Class="Sample.AI.Policies.OTelAuditPolicy"/></Policies>
///
/// Span tree independence note:
///   OTelAgent spans are emitted from ObjectScript and are independent of any
///   Rust-internal spans produced by iris-mcp-server (e.g. list_tools, call_tool,
///   ws_dispatch). There is currently no mechanism to propagate a traceparent into
///   $LLMAGENTCHAT (the $ZF callout to Rust), so MCP transport spans will appear
///   as sibling root spans in Jaeger/Tempo rather than children of the gen_ai.chat
///   span. This is a known limitation pending a new RZF ordinal or session-level
///   context in the AI Hub Rust layer.
///
/// Token field names:
///   TokenUsage struct (ai-core llm-core/src/llm.rs) uses prompt_tokens /
///   completion_tokens — consistent with what Chat() reads from tResponse.Usage.
///
/// See also: Sample.AI.Policies.OTelAuditPolicy
Class Sample.AI.OTelAgent Extends %AI.Agent
{

/// OTel audit policy — also used as the target for Traceparent propagation.
/// Created automatically in %OnNew(); reuse via UseToolSet or assign before Chat().
Property OTelPolicy As Sample.AI.Policies.OTelAuditPolicy;

Method %OnNew(provider As %AI.Provider = "") As %Status
{
    Set tSC = $$$OK
    Try {
        If $IsObject(provider) { Set ..Provider = provider }
        // Instantiate policy — reads OTEL_* env vars in its own %OnNew
        Set ..OTelPolicy = ##class(Sample.AI.Policies.OTelAuditPolicy).%New()
    } Catch {
        // Policy init failure is non-fatal — spans will use defaults
    }
    Return tSC
}

/// Override Chat() to wrap each LLM call in a gen_ai.chat span.
/// Token counts (prompt_tokens, completion_tokens) are read from response.Usage.
/// Sets OTelPolicy.Traceparent after emission so tool-call spans are children.
Method Chat(session As %AI.Agent.Session, input As %String, feedback As %RegisteredObject = "") As %AI.LLM.Response
{
    // Capture start time before the LLM call — microsecond precision via NowNs()
    Set tStartNs = ##class(Sample.AI.Policies.OTelAuditPolicy).NowNs()

    // Delegate to parent for the actual LLM call
    Set tResponse = ##super(session, input, feedback)

    // Emit gen_ai.chat span with token counts from the response
    Try {
        Set tEndNs = ##class(Sample.AI.Policies.OTelAuditPolicy).NowNs()

        // Extract token counts — IRIS SDK field names: prompt_tokens, completion_tokens
        Set tInputTokens  = 0
        Set tOutputTokens = 0
        If $IsObject(tResponse) && $IsObject(tResponse.Usage) {
            Set tInputTokens  = +tResponse.Usage.%Get("prompt_tokens")
            Set tOutputTokens = +tResponse.Usage.%Get("completion_tokens")
        }

        // Extract model name if available. $Get is not legal on a property reference —
        // it takes variables and array nodes only, and on an object it raises
        // <INVALID CLASS> "does not support MultiDimensional operations", which the
        // Catch below would swallow along with everything else. The inner Try is here
        // because the property genuinely may be absent depending on the provider.
        Set tModel = ""
        Try { If $IsObject(tResponse) { Set tModel = tResponse.Model } } Catch {}

        // Pass completion text only when content capture is enabled (PII guard)
        Set tCompletionText = ""
        If $IsObject(..OTelPolicy) && ..OTelPolicy.CaptureContent {
            Try { If $IsObject(tResponse) { Set tCompletionText = tResponse.Content } } Catch {}
        }

        Do ..EmitChatSpan(tStartNs, tEndNs, tInputTokens, tOutputTokens, tModel, tCompletionText)
    } Catch {
        // Never allow OTel emission to kill a chat response
    }

    Return tResponse
}

/// Emit a gen_ai.chat span and update OTelPolicy.Traceparent for parent-linking of tool calls.
/// startNs / endNs are nanoseconds since Unix epoch (from NowNs()).
/// completionText: when non-empty (CaptureContent=1), added as gen_ai.completion span event.
Method EmitChatSpan(startNs As %Integer, endNs As %Integer, inputTokens As %Integer, outputTokens As %Integer, model As %String, completionText As %String = "") As %Status [ Private ]
{
    Try {
        Set tStartNsStr = startNs _ ""
        Set tEndNsStr   = endNs   _ ""

        // Generate new span/trace IDs
        Set tTraceId      = ##class(Sample.AI.Policies.OTelAuditPolicy).GenHexId(32)
        Set tSpanId       = ##class(Sample.AI.Policies.OTelAuditPolicy).GenHexId(16)
        Set tParentSpanId = ""

        // If a parent traceparent exists (e.g. from ExtractTraceparent on an inbound request),
        // keep its traceId and set this chat span as a child
        If $IsObject(..OTelPolicy) && (..OTelPolicy.Traceparent '= "") {
            Set tParts = $ListFromString(..OTelPolicy.Traceparent, "-")
            If $ListLength(tParts) = 4 {
                Set tTraceId      = $ListGet(tParts, 2)
                Set tParentSpanId = $ListGet(tParts, 3)
            }
        }

        // Core gen_ai.chat attributes
        Set tAttrs = [
            {"key": "gen_ai.operation.name",      "value": {"stringValue": "chat"}},
            {"key": "gen_ai.usage.input_tokens",  "value": {"intValue": (inputTokens)}},
            {"key": "gen_ai.usage.output_tokens", "value": {"intValue": (outputTokens)}}
        ]
        If model '= "" {
            Do tAttrs.%Push({"key": "gen_ai.request.model", "value": {"stringValue": (model)}})
        }

        Set tSpanObj = {
            "traceId": (tTraceId),
            "spanId":  (tSpanId),
            "name":    "gen_ai.chat",
            "kind":    3,
            "startTimeUnixNano": (tStartNsStr),
            "endTimeUnixNano":   (tEndNsStr),
            "attributes": (tAttrs),
            "status": {"code": 1}
        }
        If tParentSpanId '= "" { Do tSpanObj.%Set("parentSpanId", tParentSpanId) }

        // Add gen_ai.completion span event when content capture is enabled
        If completionText '= "" {
            Set tEvents = [{"name": "gen_ai.completion", "attributes": [
                {"key": "gen_ai.completion", "value": {"stringValue": (completionText)}}
            ]}]
            Do tSpanObj.%Set("events", tEvents)
        }

        // Emit via the policy's PostOtlp so service.name/gen_ai.system are consistent
        If $IsObject(..OTelPolicy) {
            Do ..OTelPolicy.PostOtlp(tSpanObj)

            // Set Traceparent so subsequent tool-call spans in this turn are children
            Set ..OTelPolicy.Traceparent = "00-" _ tTraceId _ "-" _ tSpanId _ "-01"
        }
    } Catch {
        // Never propagate
    }
    Return $$$OK
}

}
