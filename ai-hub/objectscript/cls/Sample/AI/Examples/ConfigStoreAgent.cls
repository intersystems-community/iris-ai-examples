Include (%AI, %occStatus)

/// ConfigStore Agent Example
/// Demonstrates an %AI.Agent subclass whose provider and model are resolved
/// entirely from ConfigStore — no hardcoded credentials anywhere in code.
///
/// Prerequisites:
///   Run ##class(Sample.AI.Examples.ConfigStoreSetup).Run() first.
///   Set the OPENAI_API_KEY environment variable.
///
/// Run:
///   Do ##class(Sample.AI.Examples.ConfigStoreAgent).Demo()
///
/// IMPORTANT: %AI.Agent requires explicit %Init() after %New().
/// %Init() calls SettingStore.RegisterDefaults() so @{config:...} and
/// @{env:...} placeholders are resolvable, then calls %CreateProvider().
/// Without %Init(), Provider is always empty.
///
/// The PROVIDERCONFIG parameter accepts:
///   "@{config:AI.LLM.SampleOpenAI}"    — config placeholder (REQUIRED form for ConfigStore)
///   "@{env:OPENAI_API_KEY}"            — env-var placeholder in inline JSON
///
/// Note: a bare FQN ("AI.LLM.SampleOpenAI") does NOT work — %CreateProvider calls
/// SettingStore.Expand() once, which only resolves explicit @{...} placeholders.
/// A bare FQN is returned unchanged and %FromJSON fails silently leaving Provider empty.
///
/// Credentials flow:
///   ConfigStore entry → @{env:OPENAI_API_KEY} → process env at runtime
///   The API key is never stored in the database or in ObjectScript source.
Class Sample.AI.Examples.ConfigStoreAgent Extends %AI.Agent
{

/// Reference the ConfigStore LLM configuration by FQN.
/// The @{config:...} wrapper is required: %AI.Agent.%CreateProvider calls
/// SettingStore.Expand() once, which only resolves explicit placeholders.
/// A bare FQN ("AI.LLM.SampleOpenAI") is not a placeholder — Expand returns
/// it unchanged, %FromJSON fails silently, and Provider ends up empty.
/// Inner @{env:...} values in the ConfigStore entry are resolved by the
/// Rust bridge inside %AI.Provider.Create (expansion is idempotent).
Parameter PROVIDERCONFIG = "@{config:AI.LLM.SampleOpenAI}";

/// Run a simple conversation using the ConfigStore-backed provider.
ClassMethod Demo() As %Status
{
    Set tSC = $$$OK
    Try {
        Write !, "=== ConfigStore Agent Demo ===", !

        // Verify the config exists before trying to instantiate the agent
        If '##class(%ConfigStore.Configuration).Exists("AI.LLM.SampleOpenAI") {
            Write "Config 'AI.LLM.SampleOpenAI' not found.", !
            Write "Run ##class(Sample.AI.Examples.ConfigStoreSetup).Run() first.", !
            Return $$$ERROR($$$GeneralError, "ConfigStore entry not found")
        }

        // %AI.Agent requires explicit %Init() after %New().
        // %Init() calls RegisterDefaults() so @{config:...} / @{env:...} placeholders
        // are resolvable, then calls %CreateProvider() to wire up the provider.
        // Skipping %Init() leaves Provider empty regardless of PROVIDERCONFIG.
        Set tAgent = ##class(Sample.AI.Examples.ConfigStoreAgent).%New()
        Set tSC = tAgent.%Init()
        If $$$ISERR(tSC) {
            Write "Init error: ", $System.Status.GetErrorText(tSC), !
            Return tSC
        }
        Set tAgent.SystemPrompt = "You are a concise assistant. Answer in one sentence."

        // Show what was resolved
        Write "Provider resolved from ConfigStore:", !
        If $IsObject(tAgent.Provider) {
            Write "  Provider object: ", tAgent.Provider.%ClassName(1), !
        }

        // Run a simple turn
        Set tSession = tAgent.CreateSession()
        Set tResponse = tAgent.Chat(tSession, "What is 2 + 2? Answer in one sentence.")

        If $IsObject(tResponse) {
            Write "Response: ", tResponse.Content, !
            If $IsObject(tResponse.Usage) {
                Write "Tokens — prompt: ", +tResponse.Usage.%Get("prompt_tokens"),
                       ", completion: ",   +tResponse.Usage.%Get("completion_tokens"), !
            }
        }

        // ── Show how to read config details programmatically ─────────────────
        Write !, "--- Config details (secrets as placeholders) ---", !
        Set tSC = ##class(%ConfigStore.Configuration).GetDetails(
            "AI.LLM.SampleOpenAI", .tDetails,
            0,   // checkValid — skip re-validation
            0    // resolveSecrets=0 — leave @{env:...} as-is
        )
        If $$$ISERR(tSC) {
            Write "GetDetails error: ", $System.Status.GetErrorText(tSC), !
        } Else {
            Write "  model_provider : ", tDetails.%Get("model_provider"), !
            Write "  model          : ", tDetails.%Get("model"), !
            Write "  api_key        : ", tDetails.%Get("api_key"), !  // still @{env:...}
        }

        // ── Modify: swap in a different model without touching agent code ─────
        // Modify() requires %AI.ConfigStore.LLMDescriptor, which is not yet in any
        // shipped build.  Use Delete + Create (validateDetails=0) in the meantime.
        Write !, "--- Modifying config to use gpt-4o ---", !
        Set tNewDetails = {
            "model_provider": "openai",
            "model":          "gpt-4o",
            "api_key":        "@{env:OPENAI_API_KEY}"
        }
        Set tSC = ##class(%ConfigStore.Configuration).Delete("AI.LLM.SampleOpenAI")
        Set tSC = ##class(%ConfigStore.Configuration).Create(
            "AI","LLM","","SampleOpenAI",tNewDetails,"Sample OpenAI config","","","",1,0)
        If $$$ISERR(tSC) {
            Write "Update error: ", $System.Status.GetErrorText(tSC), !
        } Else {
            Write "Config updated — next agent instantiation will use gpt-4o", !
            Write "(Existing agent instances keep their resolved provider)", !
        }

        // Restore original model
        Set tOrigDetails = {
            "model_provider": "openai",
            "model":          "gpt-4o-mini",
            "api_key":        "@{env:OPENAI_API_KEY}"
        }
        Set tSC = ##class(%ConfigStore.Configuration).Delete("AI.LLM.SampleOpenAI")
        Set tSC = ##class(%ConfigStore.Configuration).Create(
            "AI","LLM","","SampleOpenAI",tOrigDetails,"Sample OpenAI config","","","",1,0)
        If $$$ISERR(tSC) {
            Write "Restore error: ", $System.Status.GetErrorText(tSC), !
        } Else {
            Write "Config restored to gpt-4o-mini", !
        }

        Set tSC = $$$OK

    } Catch ex {
        Set tSC = ex.AsStatus()
        Write "Error: ", $System.Status.GetErrorText(tSC), !
    }

    Return tSC
}

}
