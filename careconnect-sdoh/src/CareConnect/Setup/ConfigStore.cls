/// A named LLM configuration in the IRIS ConfigStore, so an agent can carry
/// `Parameter PROVIDERCONFIG = "@{config:AI.LLM.careconnect}"` instead of its own JSON blob.
///
/// Two things about %ConfigStore.Configuration are worth knowing before you copy this, both
/// measured against a bare `docker run` of the 2026.3.0AI.139.0 image (arm64, $ZV Build 139U)
/// — no source mount and no setup, so namespace USER as _SYSTEM is genuinely stock:
///
///   Create(..., validateDetails=0)   succeeds on a stock namespace
///   Create(..., validateDetails=1)   fails #26432 -> #26414 No descriptor found for AI.LLM
///   RebuildRegistry() first, then    validateDetails=1 succeeds
///
/// So %ConfigStore.DescriptorManager.RebuildRegistry() gates the validating path only. This
/// example validates: a mistyped details key is worth catching at setup rather than at the
/// first agent call, and the rebuild costs one call at startup.
///
/// The API is Create(area, type, subtype, name, details, ...). There is no Set(). An earlier
/// version of this class called %AI.ConfigStore.Set(), logged a warning when it failed, and
/// returned $$$OK anyway — so the setup log read "openai entry created" over a table holding
/// zero rows.
///
/// The stored api_key is the literal string "@{env:OPENAI_API_KEY}", resolved at read time, so
/// the credential never reaches the database or a journal file.
Class CareConnect.Setup.ConfigStore
{

/// Entry name under AI.LLM.
Parameter ENTRY = "careconnect";

/// Fully qualified name of the entry this class owns.
ClassMethod FQN() As %String
{
    Quit "AI.LLM."_..#ENTRY
}

/// Create the entry if it is absent. Idempotent — runs at every container start.
ClassMethod CreateAll() As %Status
{
    Set tSC = $$$OK
    Try {
        // First, or the validating Create below fails #26414 and the error names the
        // descriptor rather than the missing step.
        Set tSC = ##class(%ConfigStore.DescriptorManager).RebuildRegistry()
        If $$$ISERR(tSC) {
            Write "ConfigStore: descriptor registry rebuild failed: ", $System.Status.GetErrorText(tSC), !
            Return tSC
        }

        Set tFQN = ..FQN()
        If ##class(%ConfigStore.Configuration).Exists(tFQN) {
            Write "ConfigStore: ", ..Describe(), !
            Return tSC
        }

        // readResource and editResource stay empty: resource gating decides whether the
        // agent's own process can read the entry back, and that is a separate decision.
        Set tSC = ##class(%ConfigStore.Configuration).Create("AI", "LLM", "", ..#ENTRY, ..Details(), "CareConnect demo LLM endpoint", "Created by CareConnect.Setup.ConfigStore", "", "", 1, 1)
        If $$$ISERR(tSC) {
            Write "ConfigStore: create ", tFQN, " failed: ", $System.Status.GetErrorText(tSC), !
            Return tSC
        }
        // Read the row back rather than trusting the create: see the class comment.
        Write "ConfigStore: created ", ..Describe(), !
    } Catch tEx {
        Set tSC = tEx.AsStatus()
        Write "ConfigStore: ", $System.Status.GetErrorText(tSC), !
    }
    Quit tSC
}

/// The stored details. model and base_url come from the environment at setup time because the
/// agents' own PROVIDERCONFIG placeholders read the same two variables and the two have to
/// agree; api_key stays a placeholder.
ClassMethod Details() As %DynamicObject
{
    Set tDetails = {"model_provider": "openai", "api_key": "@{env:OPENAI_API_KEY}"}
    Set tModel = $System.Util.GetEnviron("OPENAI_MODEL")
    // A validating Create rejects an empty model, and an entry that cannot be created is
    // worse than one carrying the same default the compose file already interpolates.
    If tModel = "" {
        Set tModel = "gpt-4o-mini"
    }
    Set tDetails.model = tModel
    Set tBaseURL = $System.Util.GetEnviron("OPENAI_BASE_URL")
    // Omitted rather than passed empty: AI-Core rejects "" with "Invalid base URL ''"
    // instead of falling back to the provider default.
    If tBaseURL '= "" {
        Set tDetails."base_url" = tBaseURL
    }
    Quit tDetails
}

/// What is actually stored, as JSON: fqn, exists, model, base_url, api_key, error.
ClassMethod Describe() As %String
{
    Set tOut = {}
    Set tOut.fqn = ..FQN()
    Set tOut.exists = 0
    Set tOut.error = ""
    Try {
        If '##class(%ConfigStore.Configuration).Exists(tOut.fqn) {
            Set tOut.error = "not present in %ConfigStore.Configuration"
            Return tOut.%ToJSON()
        }
        Set tOut.exists = 1
        // The trailing 0,0 leave secrets unresolved: the point of the check is that the
        // stored value is still a placeholder, not what it resolves to.
        Set tSC = ##class(%ConfigStore.Configuration).GetDetails(tOut.fqn, .tDetails, 0, 0)
        If $$$ISERR(tSC) {
            Set tOut.error = $System.Status.GetErrorText(tSC)
            Return tOut.%ToJSON()
        }
        Set tOut."api_key" = tDetails.%Get("api_key")
        Set tOut.model = tDetails.%Get("model")
        Set tOut."base_url" = tDetails.%Get("base_url", "")
    } Catch tEx {
        Set tOut.error = tEx.DisplayString()
    }
    Quit tOut.%ToJSON()
}

/// Delete the entry. Demo reset, and the teardown half of a test that creates it.
ClassMethod Remove() As %Status
{
    Set tSC = $$$OK
    Try {
        Set tFQN = ..FQN()
        If '##class(%ConfigStore.Configuration).Exists(tFQN) {
            Write "ConfigStore: ", tFQN, " absent, nothing to remove", !
            Return tSC
        }
        Set tSC = ##class(%ConfigStore.Configuration).Delete(tFQN)
        If $$$ISERR(tSC) {
            Write "ConfigStore: delete ", tFQN, " failed: ", $System.Status.GetErrorText(tSC), !
            Return tSC
        }
        Write "ConfigStore: deleted ", tFQN, !
    } Catch tEx {
        Set tSC = tEx.AsStatus()
        Write "ConfigStore: ", $System.Status.GetErrorText(tSC), !
    }
    Quit tSC
}

}
