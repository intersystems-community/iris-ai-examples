Include (%AI, %occStatus)

/// ConfigStore Setup Example
/// Shows how to register LLM and MCP server configurations in the AI Hub ConfigStore
/// so agents and toolsets can reference them by name instead of hardcoding credentials.
///
/// Run from terminal:
///   Do ##class(Sample.AI.Examples.ConfigStoreSetup).Run()
///
/// After running, agents can use:
///   Parameter PROVIDERCONFIG = "@{config:AI.LLM.SampleOpenAI}";
///
/// Note: use the @{config:...} form, not the bare FQN.  %AI.Agent.%CreateProvider
/// calls SettingStore.Expand() which only resolves explicit @{...} placeholders;
/// a bare FQN is returned unchanged and %FromJSON fails silently.
///
/// Or from ObjectScript:
///   Set tSC = ##class(%ConfigStore.Configuration).Use("AI.LLM.SampleOpenAI")
///
/// Cleanup:
///   Do ##class(Sample.AI.Examples.ConfigStoreSetup).Cleanup()
Class Sample.AI.Examples.ConfigStoreSetup Extends %RegisteredObject
{

/// Register sample LLM and MCP configurations in the ConfigStore.
/// API key is read from the OPENAI_API_KEY environment variable.
ClassMethod Run() As %Status
{
    Set tSC = $$$OK
    Try {
        Write !, "=== ConfigStore Setup Example ===", !

        // ── 1. LLM configuration ─────────────────────────────────────────────
        // Store the provider config with the API key as an env-var placeholder.
        // The @{env:...} syntax means the key is never stored in the database —
        // it is resolved at runtime from the process environment.

        Set tLLMFQN = "AI.LLM.SampleOpenAI"

        If ##class(%ConfigStore.Configuration).Exists(tLLMFQN) {
            Write "LLM config '", tLLMFQN, "' already exists — skipping create", !
        } Else {
            Set tLLMDetails = {
                "model_provider": "openai",
                "model":          "gpt-4o-mini",
                "api_key":        "@{env:OPENAI_API_KEY}"
            }

            // validateDetails=0: %AI.ConfigStore.LLMDescriptor is not yet in any
            // shipped build.  The config stores and resolves correctly without it —
            // validation is advisory.  Flip to 1 once descriptors land.
            Set tSC = ##class(%ConfigStore.Configuration).Create(
                "AI",               // area
                "LLM",              // type
                "",                 // subtype
                "SampleOpenAI",     // name  → FQN = AI.LLM.SampleOpenAI
                tLLMDetails,
                "Sample OpenAI config",
                "Created by Sample.AI.Examples.ConfigStoreSetup",
                "",                 // readResource
                "",                 // editResource
                1,                  // enabled
                0                   // validateDetails
            )
            If $$$ISERR(tSC) {
                Write "Error creating LLM config: ", $System.Status.GetErrorText(tSC), !
                Return tSC
            }
            Write "Created LLM config: ", tLLMFQN, !
        }

        // Verify the LLM config round-trips correctly
        Set tSC = ##class(%ConfigStore.Configuration).GetDetails(tLLMFQN, .tLLMOut, 0, 0)
        If $$$ISERR(tSC) {
            Write "Error reading LLM config: ", $System.Status.GetErrorText(tSC), !
            Return tSC
        }
        Write "  model_provider : ", tLLMOut.%Get("model_provider"), !
        Write "  model          : ", tLLMOut.%Get("model"), !
        Write "  api_key        : ", tLLMOut.%Get("api_key"), !  // still placeholder form

        // ── 2. MCP server configuration (stdio transport) ────────────────────
        // Register the IRIS MCP server binary as a named, reusable config.
        // Agents that need it reference "AI.MCP.LocalIRISMCP" — no path hardcoded
        // in agent code.

        Set tMCPFQN = "AI.MCP.LocalIRISMCP"

        If ##class(%ConfigStore.Configuration).Exists(tMCPFQN) {
            Write "MCP config '", tMCPFQN, "' already exists — skipping create", !
        } Else {
            // iris-mcp-server ships in $ISC_PACKAGE_INSTALLDIR/bin
            // Use @{env:...} so the path works on any install layout
            Set tMCPDetails = {
                "transport": "stdio",
                "command":   "@{env:ISC_PACKAGE_INSTALLDIR}/bin/iris-mcp-server",
                "args":      ["--namespace", "@{env:IRISNAMESPACE}"],
                "env":       {
                    "IRIS_MCP_LOG_LEVEL": "warn"
                }
            }

            Set tSC = ##class(%ConfigStore.Configuration).Create(
                "AI",
                "MCP",
                "",
                "LocalIRISMCP",
                tMCPDetails,
                "Local IRIS MCP server (stdio)",
                "Created by Sample.AI.Examples.ConfigStoreSetup",
                "", "", 1, 0    // validateDetails=0 — descriptor not yet shipped
            )
            If $$$ISERR(tSC) {
                Write "Error creating MCP config: ", $System.Status.GetErrorText(tSC), !
                Return tSC
            }
            Write "Created MCP config: ", tMCPFQN, !
        }

        // Verify the MCP config
        Set tSC = ##class(%ConfigStore.Configuration).GetDetails(tMCPFQN, .tMCPOut, 0, 0)
        If $$$ISERR(tSC) {
            Write "Error reading MCP config: ", $System.Status.GetErrorText(tSC), !
            Return tSC
        }
        Write "  transport : ", tMCPOut.%Get("transport"), !
        Write "  command   : ", tMCPOut.%Get("command"), !

        // ── 3. MCP server configuration (remote/HTTP transport) ──────────────
        // Example for a remote MCP server reached over HTTP with bearer auth.

        Set tRemoteFQN = "AI.MCP.RemoteMCPExample"

        If ##class(%ConfigStore.Configuration).Exists(tRemoteFQN) {
            Write "Remote MCP config '", tRemoteFQN, "' already exists — skipping create", !
        } Else {
            Set tRemoteDetails = {
                "transport": "remote",
                "url":       "https://mcp.example.com/sse",
                "auth": {
                    "type":  "bearer",
                    "token": "@{env:MCP_BEARER_TOKEN}"
                }
            }

            // Build 139+: remote MCP tools require bearer/basic auth headers.
            // This example already has the correct pattern with @{env:MCP_BEARER_TOKEN}.
            Set tSC = ##class(%ConfigStore.Configuration).Create(
                "AI",
                "MCP",
                "",
                "RemoteMCPExample",
                tRemoteDetails,
                "Remote MCP server example (bearer auth)",
                "Created by Sample.AI.Examples.ConfigStoreSetup",
                "", "", 1, 0    // validateDetails=0 — descriptor not yet shipped
            )
            If $$$ISERR(tSC) {
                Write "Error creating remote MCP config: ", $System.Status.GetErrorText(tSC), !
                Return tSC
            }
            Write "Created remote MCP config: ", tRemoteFQN, !
        }

        // ── 4. Summary ───────────────────────────────────────────────────────
        Write !, "--- Registered configurations ---", !
        Write "  ", tLLMFQN,    " (LLM — openai gpt-4o-mini, key from env)", !
        Write "  ", tMCPFQN,    " (MCP — stdio, local iris-mcp-server)", !
        Write "  ", tRemoteFQN, " (MCP — remote bearer, example only)", !
        Write !, "Agents can now use:", !
        Write "  Parameter PROVIDERCONFIG = ""@{config:", tLLMFQN, "}"";", !
        Write !, "Run Cleanup() to remove these configurations.", !

    } Catch ex {
        Set tSC = ex.AsStatus()
        Write "Error: ", $System.Status.GetErrorText(tSC), !
    }

    Return tSC
}

/// Remove the configurations created by Run().
ClassMethod Cleanup() As %Status
{
    Set tSC = $$$OK
    For tFQN = "AI.LLM.SampleOpenAI", "AI.MCP.LocalIRISMCP", "AI.MCP.RemoteMCPExample" {
        If ##class(%ConfigStore.Configuration).Exists(tFQN) {
            Set tSC = ##class(%ConfigStore.Configuration).Delete(tFQN)
            If $$$ISERR(tSC) {
                Write "Error deleting ", tFQN, ": ", $System.Status.GetErrorText(tSC), !
            } Else {
                Write "Deleted ", tFQN, !
            }
        } Else {
            Write tFQN, " not found — skipping", !
        }
    }
    Return tSC
}

}
