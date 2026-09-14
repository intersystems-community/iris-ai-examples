Include (%AI, %occStatus)

/// Portable OTel audit policy for IRIS AI Hub.
/// Emits gen_ai.* semantic convention spans via OTLP/HTTP for every tool invocation.
///
/// Attach to any ToolSet via the XML <Policies> section, as a self-closing element
/// named for the policy kind with a Class attribute:
///   <Policies>
///     <Audit Class="Sample.AI.Policies.OTelAuditPolicy"/>
///   </Policies>
/// The <Policy><ClassName>...</ClassName></Policy> form this comment used to give is
/// not the shape the spec parses, and a spec it cannot parse fails silently.
///
/// Measured on the MCP tool-call path (external client -> iris-mcp-server ->
/// %AI.MCP.Service) on 2026.3.0AI build 139U: %LogExecution is called once per
/// tools/call, but the framework passes duration = 0 and the literal call id
/// "call_id", so startTimeUnixNano equals endTimeUnixNano and gen_ai.tool.call_id
/// does not correlate anything. Both carry real values on the %AI.Agent path.
///
/// Configuration (environment variables, read at execution time):
///   OTEL_EXPORTER_OTLP_ENDPOINT  OTLP/HTTP traces endpoint (default: http://localhost:4318/v1/traces)
///   OTEL_SERVICE_NAME            service.name resource attribute (default: iris-ai-agent)
///   OTEL_GENAI_SYSTEM            gen_ai.system resource attribute (default: iris)
///   OTEL_CAPTURE_CONTENT         Set to "true" to capture prompt/completion text in span events
///
/// Traceparent propagation:
///   Set policy.Traceparent = "00-<traceId>-<parentSpanId>-01" before agent run.
///   Tool-call spans become children of that trace context. When empty, starts a new root trace.
///   Use ExtractTraceparent(%request) to pull the W3C header from an inbound REST call.
///   OTelAgent sets Traceparent automatically after each Chat() span.
Class Sample.AI.Policies.OTelAuditPolicy Extends %AI.Policy.Audit
{

/// Controls how spans are exported.
///   Http  — POST to OtlpEndpoint (default, production)
///   Log   — Write span JSON to IRIS messages log (useful in test subclasses)
///   Noop  — Discard silently (disable all export)
///
/// Override in a test subclass:
///   Class Test.NoopAuditPolicy Extends Sample.AI.Policies.OTelAuditPolicy
///   { Parameter EXPORTER = "Noop"; }
Parameter EXPORTER As STRING = "Http";

/// W3C traceparent of the parent span. Set by caller before agent run.
/// OTelAgent sets this after emitting each chat span so tool-call spans become children.
/// No globals — per-instance, concurrent-safe.
Property Traceparent As %String;

/// OTLP/HTTP traces endpoint. Populated from OTEL_EXPORTER_OTLP_ENDPOINT on %New().
Property OtlpEndpoint As %String [ InitialExpression = "http://localhost:4318/v1/traces" ];

/// service.name resource attribute. Populated from OTEL_SERVICE_NAME on %New().
Property ServiceName As %String [ InitialExpression = "iris-ai-agent" ];

/// gen_ai.system resource attribute. Populated from OTEL_GENAI_SYSTEM on %New().
Property GenAiSystem As %String [ InitialExpression = "iris" ];

/// When true, captures prompt arguments and result text as span events.
/// Default false — PII guard. Set OTEL_CAPTURE_CONTENT=true to enable.
Property CaptureContent As %Boolean [ InitialExpression = 0 ];

Method %OnNew() As %Status
{
    Set tSC = $$$OK
    Try {
        Set tEndpoint = $System.Util.GetEnviron("OTEL_EXPORTER_OTLP_ENDPOINT")
        If tEndpoint '= "" { Set ..OtlpEndpoint = tEndpoint }

        Set tSvcName = $System.Util.GetEnviron("OTEL_SERVICE_NAME")
        If tSvcName '= "" { Set ..ServiceName = tSvcName }

        Set tSystem = $System.Util.GetEnviron("OTEL_GENAI_SYSTEM")
        If tSystem '= "" { Set ..GenAiSystem = tSystem }

        Set tCapture = $System.Util.GetEnviron("OTEL_CAPTURE_CONTENT")
        If $ZConvert(tCapture, "L") = "true" { Set ..CaptureContent = 1 }
    } Catch {
        // Env read failures are non-fatal — use defaults
    }
    Return tSC
}

/// Called by the Rust layer (IrisAuditPolicy::log_denial) when %CanExecute denies a tool call.
/// Emits a gen_ai.tool_call span with status.code=2 and gen_ai.tool.denied=true so denials
/// are visible in OTel traces alongside successful executions.
///
/// %Get already returns "" for an absent key, so do not wrap it in $Get — see the
/// note on %LogExecution for what that cost.
Method %LogDenial(call As %DynamicObject, metadata As %DynamicObject, status As %Status) As %Status
{
    Try {
        Set tToolName = call.%Get("name")
        Set tCallId   = call.%Get("id")
        Set tErrMsg   = $System.Status.GetErrorText(status)
        Do ..EmitDenialSpan(tToolName, tCallId, tErrMsg)
    } Catch {
        // OTel emission failures must never propagate to the caller
    }
    Return $$$OK
}

/// Emit a gen_ai.tool_call span marking a policy denial. status.code=2 (ERROR),
/// gen_ai.tool.denied=true distinguishes denials from execution errors in dashboards.
Method EmitDenialSpan(toolName As %String, callId As %String, reason As %String) As %Status [ Private ]
{
    Try {
        Set tNowNs    = ..NowNs()
        Set tNowStr   = tNowNs _ ""

        Set tTraceId      = ..GenHexId(32)
        Set tSpanId       = ..GenHexId(16)
        Set tParentSpanId = ""

        If ..Traceparent '= "" {
            Set tParts = $ListFromString(..Traceparent, "-")
            If $ListLength(tParts) = 4 {
                Set tTraceId      = $ListGet(tParts, 2)
                Set tParentSpanId = $ListGet(tParts, 3)
            }
        }

        Set tOpName = "execute_tool " _ toolName
        Set tAttrs = [
            {"key": "gen_ai.operation.name", "value": {"stringValue": (tOpName)}},
            {"key": "gen_ai.tool.name",      "value": {"stringValue": (toolName)}},
            {"key": "gen_ai.tool.call_id",   "value": {"stringValue": (callId)}},
            {"key": "gen_ai.tool.denied",    "value": {"boolValue": true}},
            {"key": "exception.message",     "value": {"stringValue": (reason)}}
        ]

        Set tSpanObj = {
            "traceId": (tTraceId),
            "spanId":  (tSpanId),
            "name":    (tOpName),
            "kind":    3,
            "startTimeUnixNano": (tNowStr),
            "endTimeUnixNano":   (tNowStr),
            "attributes": (tAttrs),
            "status": {"code": 2}
        }
        If tParentSpanId '= "" { Do tSpanObj.%Set("parentSpanId", tParentSpanId) }

        Do ..Export(tSpanObj)
    } Catch {
        // Never propagate
    }
    Return $$$OK
}

/// The second line used to read `Set tCallId = $Get(call.%Get("id"), "")`, and that
/// one call to $Get meant this policy emitted no span, ever. $Get takes a variable or
/// an array node, never an object expression, so it raised
/// <INVALID CLASS> ... Class '%Library.DynamicObject' does not support MultiDimensional
/// operations on every tool call — and the Catch below, which exists so that a dead
/// collector cannot break a tool, swallowed it identically. The measurable symptom was
/// no spans and no errors anywhere. %Get already returns "" for an absent key, so the
/// $Get bought nothing in exchange. Measured on 2026.3.0AI build 139U by overriding
/// this method in a subclass whose Catch reported instead of swallowing.
///
/// The lesson generalizes past this file: a fire-and-forget Catch around a whole span
/// builder converts an ordinary coding error into an invisible one. Keep the swallow,
/// but keep the body it wraps small enough to read.
Method %LogExecution(call As %DynamicObject, metadata As %DynamicObject, result As %DynamicObject, duration As %Integer, status As %Status) As %Status
{
    Try {
        Set tToolName = call.%Get("name")
        Set tCallId   = call.%Get("id")
        Do ..EmitToolCallSpan(tToolName, tCallId, duration, $$$ISOK(status), status, call, result)
    } Catch {
        // OTel emission failures must never propagate to the caller
    }
    Return $$$OK
}

/// Emit a gen_ai.tool_call span via OTLP/HTTP. Fire-and-forget — 1s timeout.
Method EmitToolCallSpan(toolName As %String, callId As %String, durationMs As %Integer, success As %Boolean, status As %Status, call As %DynamicObject, result As %DynamicObject) As %Status [ Private ]
{
    Try {
        Set tEndNs      = ..NowNs()
        Set tStartNs    = tEndNs - (durationMs * 1000000)
        Set tEndNsStr   = tEndNs _ ""
        Set tStartNsStr = tStartNs _ ""

        // Generate IDs — override from Traceparent if set
        Set tTraceId      = ..GenHexId(32)
        Set tSpanId       = ..GenHexId(16)
        Set tParentSpanId = ""

        If ..Traceparent '= "" {
            Set tParts = $ListFromString(..Traceparent, "-")
            If $ListLength(tParts) = 4 {
                Set tTraceId      = $ListGet(tParts, 2)
                Set tParentSpanId = $ListGet(tParts, 3)
            }
        }

        Set tStatusCode = $Select(success:1, 1:2)  // 1=OK, 2=ERROR per OTLP proto

        // Core attributes
        Set tAttrs = [
            {"key": "gen_ai.operation.name", "value": {"stringValue": "tool_call"}},
            {"key": "gen_ai.tool.name",       "value": {"stringValue": (toolName)}},
            {"key": "gen_ai.tool.call_id",    "value": {"stringValue": (callId)}},
            {"key": "gen_ai.tool.duration_ms","value": {"intValue": (durationMs)}},
            {"key": "gen_ai.tool.success",    "value": {"boolValue": (success)}}
        ]

        // Error attributes
        If 'success {
            Set tErrMsg = $System.Status.GetErrorText(status)
            Do tAttrs.%Push({"key": "exception.message", "value": {"stringValue": (tErrMsg)}})
        }

        // Span events for content capture (opt-in)
        Set tEvents = []
        If ..CaptureContent && $IsObject(call) {
            Set tArgJson = ""
            If $IsObject(call.%Get("arguments")) {
                Set tArgJson = call.%Get("arguments").%ToJSON()
            } ElseIf call.%Get("arguments") '= "" {
                Set tArgJson = call.%Get("arguments")
            }
            If tArgJson '= "" {
                Do tEvents.%Push({"name": "gen_ai.prompt", "attributes": [
                    {"key": "gen_ai.prompt", "value": {"stringValue": (tArgJson)}}
                ]})
            }
        }

        Set tSpanObj = {
            "traceId": (tTraceId),
            "spanId":  (tSpanId),
            "name":    ("execute_tool " _ toolName),
            "kind":    3,
            "startTimeUnixNano": (tStartNsStr),
            "endTimeUnixNano":   (tEndNsStr),
            "attributes": (tAttrs),
            "status": {"code": (tStatusCode)}
        }
        If tParentSpanId '= "" { Do tSpanObj.%Set("parentSpanId", tParentSpanId) }
        If tEvents.%Size() > 0 { Do tSpanObj.%Set("events", tEvents) }

        Do ..Export(tSpanObj)
    } Catch {
        // Never propagate
    }
    Return $$$OK
}

/// Dispatch a span to the configured exporter.
/// Override EXPORTER parameter in a subclass to redirect without touching PostOtlp.
///
/// The "Log" branch writes to messages.log through %SYS.System, not through
/// $$$LOGMESSAGE. That macro is defined by the Ensemble include, which this class
/// does not pull in, so the version that used it failed to COMPILE — not to run —
/// with MPP5610 "Referenced macro not defined: 'LOGMESSAGE'". Because the failure
/// is at compile time it bit every user of the class regardless of EXPORTER, even
/// though the default is "Http" and this branch is unreachable by default.
/// Measured on 2026.3.0AI build 139U.
Method Export(spanObj As %DynamicObject) As %Status [ Private ]
{
    If ..#EXPORTER = "Noop" { Return $$$OK }
    If ..#EXPORTER = "Log" {
        Do ##class(%SYS.System).WriteToConsoleLog("OTelAuditPolicy span: " _ spanObj.%ToJSON())
        Return $$$OK
    }
    Return ..PostOtlp(spanObj)
}

/// POST a single span to the OTLP/HTTP endpoint. 1s timeout, fire-and-forget.
Method PostOtlp(spanObj As %DynamicObject) As %Status [ Private ]
{
    Try {
        Set tPayload = {
            "resourceSpans": [{
                "resource": {
                    "attributes": [
                        {"key": "service.name",  "value": {"stringValue": (..ServiceName)}},
                        {"key": "gen_ai.system", "value": {"stringValue": (..GenAiSystem)}}
                    ]
                },
                "scopeSpans": [{
                    "scope": {"name": "iris-llm"},
                    "spans": [(spanObj)]
                }]
            }]
        }

        // Parse the endpoint URL robustly via %Net.URLParser to handle non-standard
        // ports and paths (e.g. http://collector:4317/custom/v1/traces).
        Set tEndpoint = ..OtlpEndpoint
        Set tReq = ##class(%Net.HttpRequest).%New()
        Set tReq.Https   = $Select(tEndpoint [ "https://":1, 1:0)
        Set tReq.Timeout = 1
        Do tReq.SetHeader("Content-Type", "application/json")
        Do tReq.EntityBody.Write(tPayload.%ToJSON())

        // Strip scheme to get "host:port/path"
        Set tNoScheme = $Piece(tEndpoint, "//", 2, *)
        // Split on first "/" to separate authority from path
        Set tAuthority = $Piece(tNoScheme, "/", 1)
        Set tRawPath   = "/" _ $Piece(tNoScheme, "/", 2, *)
        If tRawPath = "/" { Set tRawPath = "/v1/traces" }
        // Split authority on last ":" for host:port (handles IPv4; no IPv6 brackets needed here)
        Set tColonPos = $Length(tAuthority) - $Length($Piece(tAuthority, ":", *)) - $Length(":")
        If tColonPos > 0 && ($Piece(tAuthority, ":", *) ? 1.N) {
            Set tReq.Server = $Extract(tAuthority, 1, tColonPos)
            Set tReq.Port   = +$Piece(tAuthority, ":", *)
        } Else {
            Set tReq.Server = tAuthority
            Set tReq.Port   = $Select(tReq.Https:443, 1:4318)
        }
        Do tReq.Post(tRawPath)
    } Catch {
        // Network failures are non-fatal
    }
    Return $$$OK
}

/// Current UTC time as integer nanoseconds since Unix epoch.
/// Uses $ZTimeStamp fractional seconds (microsecond precision) — far better than
/// the second-resolution DATEDIFF approach. $ZTimeStamp format: ddddd,sssss.ffffff
/// where ddddd = days since 31-Dec-1840, sssss = seconds in day, ffffff = fraction.
ClassMethod NowNs() As %Integer
{
    // Days from 31-Dec-1840 to 1-Jan-1970 = 47117
    Set tTs      = $ZTimeStamp
    Set tDays    = $Piece(tTs, ",", 1) - 47117
    Set tSecFrac = $Piece(tTs, ",", 2)           // "sssss.ffffff"
    Set tSec     = $Piece(tSecFrac, ".", 1) + (tDays * 86400)
    Set tFrac    = $Piece(tSecFrac, ".", 2)       // up to 6 digits
    // Pad to 9 digits for nanoseconds (last 3 are zero — IRIS gives microseconds)
    Set tFracNs  = $Extract(tFrac _ "000000000", 1, 9)
    Return (tSec * 1000000000) + tFracNs
}

/// Extract a W3C traceparent from an inbound %CSP.Request and store it on this policy.
/// Call this at the top of any REST dispatch method that will run an AI agent:
///
///   Do policy.ExtractTraceparent(%request)
///
/// If no traceparent header is present the property is left unchanged (empty = new root trace).
/// Returns 1 if a valid traceparent was found and stored, 0 otherwise.
Method ExtractTraceparent(request As %CSP.Request) As %Boolean
{
    Try {
        Set tHeader = request.GetCgiEnv("HTTP_TRACEPARENT")
        If tHeader = "" { Return 0 }
        // Validate: "00-<32hex>-<16hex>-<2hex>"
        Set tParts = $ListFromString(tHeader, "-")
        If $ListLength(tParts) = 4
         && ($Length($ListGet(tParts, 2)) = 32)
         && ($Length($ListGet(tParts, 3)) = 16) {
            Set ..Traceparent = tHeader
            Return 1
        }
    } Catch {
    }
    Return 0
}

/// Generate a lowercase hex random ID of exactly len characters.
/// Uses $System.Encryption.GenRandom for adequate entropy; falls back to $Random.
ClassMethod GenHexId(len As %Integer) As %String
{
    Set tResult   = ""
    Set tHexChars = "0123456789abcdef"
    Try {
        Set tBytes = $System.Encryption.GenRandom(len \ 2)
        For i = 1:1:$Length(tBytes) {
            Set tByte   = $Ascii(tBytes, i)
            Set tResult = tResult _ $Extract(tHexChars, (tByte \ 16) + 1) _ $Extract(tHexChars, (tByte # 16) + 1)
        }
        Set tResult = $Extract(tResult _ $Translate($Justify("", len), " ", "0"), 1, len)
    } Catch {
        For i = 1:1:len {
            Set tResult = tResult _ $Extract(tHexChars, $Random(16) + 1)
        }
    }
    Return tResult
}

}
