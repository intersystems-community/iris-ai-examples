/// The instance's LLM endpoint: what the agents resolve, and whether it answers.
///
/// Replaces CareConnect.Setup.ConfigStore, which called %AI.ConfigStore.Set(). That method
/// does not exist on this build — the API is Create(area,type,subtype,name,details) — and
/// CreateEntry() logged a warning then returned $$$OK, so the setup log read "openai entry
/// created" while %ConfigStore.Configuration held zero rows. Nothing noticed, because the
/// agents never read those entries: they carry PROVIDERCONFIG.
///
/// This class is deliberately not a config writer. It reports the endpoint the agents'
/// @{env:...} placeholders resolve to, and proves it answers.
Class CareConnect.Setup.LLMConfig
{

/// The provider settings the agents' PROVIDERCONFIG placeholders resolve to. Kept in sync
/// with those parameters by hand — a class method cannot be called from a Parameter.
ClassMethod Settings() As %DynamicObject
{
    Set tSettings = {"model_provider": "openai"}
    Set tSettings.model = $System.Util.GetEnviron("OPENAI_MODEL")
    Set tSettings."api_key" = $System.Util.GetEnviron("OPENAI_API_KEY")
    Set tBaseURL = $System.Util.GetEnviron("OPENAI_BASE_URL")
    // Omitted rather than passed empty: AI-Core rejects "" with "Invalid base URL '':
    // relative URL without a base" instead of falling back to the provider default.
    If tBaseURL '= "" {
        Set tSettings."base_url" = tBaseURL
    }
    Quit tSettings
}

/// Write the resolved endpoint into the setup log. Worth a line of its own: an agent
/// failing against an endpoint nobody configured reads as a transport fault, and the
/// error names a host rather than a setting.
ClassMethod Describe() As %Status
{
    Set tSC = $$$OK
    Set tSettings = ..Settings()
    Set tKeyState = $Select($System.Util.GetEnviron("OPENAI_API_KEY") '= "": "set", 1: "MISSING")
    Write "LLM endpoint: provider=openai model=", tSettings.model
    Write " base_url=", tSettings.%Get("base_url", "(provider default)")
    Write " api_key=", tKeyState, !
    Quit tSC
}

/// Does the configured endpoint answer from inside this container? Returns JSON with
/// ok, base_url, model and error.
///
/// The cheap falsifying experiment. Without it an unroutable endpoint surfaces as a dozen
/// agent tests failing eight seconds apart on a transport error, which is not how anyone
/// reads "wrong host".
ClassMethod Probe() As %String
{
    Set tSC = $$$OK
    Set tSettings = ..Settings()
    Set tOut = {}
    Set tOut.ok = 0
    Set tOut.error = ""
    Set tOut.model = tSettings.model
    Set tOut."base_url" = tSettings.%Get("base_url", "")
    // Checked before the call because the failure it causes says nothing: AI-Core joins
    // "chat/completions" onto base_url with URL-relative semantics, so ".../v1" resolves
    // to ".../chat/completions" and the endpoint answers HTTP 500 with an empty body.
    // ".../v1/" resolves correctly.
    If (tOut."base_url" '= "") && ($Extract(tOut."base_url", *) '= "/") {
        Set tOut.error = "OPENAI_BASE_URL must end in '/' — AI-Core resolves chat/completions against it as a relative URL and would drop its last path segment"
        Quit tOut.%ToJSON()
    }
    Try {
        Set tProvider = ##class(%AI.Provider).Create("openai", tSettings)
        Set tResponse = tProvider.ChatComplete(tSettings.model, [{"role": "user", "content": "ping"}])
        If $IsObject(tResponse) {
            Set tOut.ok = 1
        } Else {
            Set tOut.error = "provider returned no response object"
        }
    } Catch tEx {
        Set tOut.error = tEx.DisplayString()
    }
    Quit tOut.%ToJSON()
}

}
