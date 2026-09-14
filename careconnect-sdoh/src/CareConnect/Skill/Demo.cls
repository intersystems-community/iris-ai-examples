/// CareConnect Skill Demo
///
/// Shows the difference between wiring the contradiction gate manually
/// (via SDoHAssessment subclass) vs. loading it as a reusable skill
/// (one line: agent.UseSkill("CareConnect.Skill.ContradictionGate")).
///
/// Usage:
///   Do ##class(CareConnect.Skill.Demo).RunAll()
///   Do ##class(CareConnect.Skill.Demo).SkillDemo()
///   Do ##class(CareConnect.Skill.Demo).CompareApproaches()
Class CareConnect.Skill.Demo
{

// ---------------------------------------------------------------------------
// Shared setup
// ---------------------------------------------------------------------------

ClassMethod CreateBaseAgent(Output agent As %AI.Agent) As %Status [ Private ]
{
    Set apiKey = ##class(Sample.AI.Utils).GetAPIKey("openai", .providerType)
    If apiKey = "" Set apiKey = ##class(Sample.AI.Utils).GetAPIKey("anthropic", .providerType)
    If apiKey = "" Quit $$$ERROR($$$GeneralError, "No API key — set OPENAI_API_KEY or ANTHROPIC_API_KEY")

    Set model = $Select(providerType="anthropic":"claude-sonnet-4-6", 1:"gpt-4o-mini")
    Set config = {"api_key": (apiKey)}
    // Same reason the agents carry PROVIDERCONFIG: an api_key does not say where to send
    // the request, so on a host with no route to api.openai.com this demo dies on a
    // connection reset. The base URL must end in "/" — see CareConnect.Setup.LLMConfig.
    // The model comes with it: an OpenAI-compatible endpoint serves its own list, and
    // gpt-4o-mini is not always on it.
    If providerType = "openai" {
        Set baseURL = $System.Util.GetEnviron("OPENAI_BASE_URL")
        Set envModel = $System.Util.GetEnviron("OPENAI_MODEL")
        If baseURL '= "" Set config."base_url" = baseURL
        If envModel '= "" Set model = envModel
    }
    Set provider = ##class(%AI.Provider).Create(providerType, config)

    Set agent = ##class(%AI.Agent).%New(provider)
    Set agent.Model = model
    Set agent.SystemPrompt = "You are a community health worker assistant."

    // Register the SDoH toolset — tools available to all approaches
    Set toolset = ##class(CareConnect.Tools.SDoHToolSet).%New()
    Do agent.ToolManager.AddTool(toolset)

    Quit $$$OK
}

// ---------------------------------------------------------------------------
// Demo 1: Manual wiring (the old way)
// ---------------------------------------------------------------------------

/// Manual approach: contradiction gate embedded in SDoHAssessment subclass.
/// The policy is baked into INSTRUCTIONS — not reusable across agents.
ClassMethod ManualDemo() As %Status
{
    Try {
        Write !, "=== Approach A: Manual (SDoHAssessment subclass) ===", !
        Write "Gate policy is in INSTRUCTIONS — works, but not portable.", !, !

        // SDoHAssessment has the gate baked into its XData INSTRUCTIONS
        Set agent = ##class(CareConnect.Agent.SDoHAssessment).%New()
        $$$ThrowOnError(agent.%Init())
        Set session = agent.CreateSession()

        Write "Q: What threshold for food insecurity screening?", !
        Set response = agent.Chat(session, "What threshold should I use to screen a patient for food insecurity?")
        Do ##class(%AI.System).RenderMarkdown(response.Content)
        Write !, "Tool calls: ", session.GetStats()."total_tool_calls", !

        Return $$$OK
    } Catch ex {
        Write "Error: ", ex.DisplayString(), !
        Return ex.AsStatus()
    }
}

// ---------------------------------------------------------------------------
// Demo 2: UseSkill — one line, portable
// ---------------------------------------------------------------------------

/// Skill approach: any base agent loads the gate with one line.
/// Same behavior, zero subclassing — the skill IS the policy.
ClassMethod SkillDemo() As %Status
{
    Try {
        Write !, "=== Approach B: UseSkill (portable, one line) ===", !
        Write "agent.UseSkill(""CareConnect.Skill.ContradictionGate"")", !
        Write "Gate behavior injected into any agent. No subclassing.", !, !

        $$$ThrowOnError(..CreateBaseAgent(.agent))

        // THE KEY LINE — this is what makes it a skill vs. a hardcoded policy
        $$$ThrowOnError(agent.UseSkill("CareConnect.Skill.ContradictionGate"))

        Write "Agent skills loaded: "
        // List active skills if the API supports it
        If $IsObject(agent.Skills) {
            Set iter = agent.Skills.%GetIterator()
            While iter.%GetNext(.k, .skill) { Write skill.Name, " " }
        }
        Write !, !

        Set session = agent.CreateSession()

        Write "Q: What threshold for food insecurity screening?", !
        Set response = agent.Chat(session, "What threshold should I use to screen a patient for food insecurity?")
        Do ##class(%AI.System).RenderMarkdown(response.Content)
        Write !, "Tool calls: ", session.GetStats()."total_tool_calls", !
        Write "(Expected: gate fired, BLOCKED returned, no recommendation made)", !

        Return $$$OK
    } Catch ex {
        Write "Error: ", ex.DisplayString(), !
        Return ex.AsStatus()
    }
}

// ---------------------------------------------------------------------------
// Demo 3: Side-by-side comparison (talk slide)
// ---------------------------------------------------------------------------

/// Shows the structural difference between the two approaches.
/// No LLM needed — prints code patterns only. Good for talk slides.
ClassMethod CompareApproaches() As %Status
{
    Write !, "╔══════════════════════════════════════════════════════╗", !
    Write "║  Skills vs. Manual Wiring — Side by Side             ║", !
    Write "╚══════════════════════════════════════════════════════╝", !

    Write !, "── Approach A: Manual (SDoHAssessment) ───────────────", !
    Write "  Class CareConnect.Agent.SDoHAssessment Extends %AI.Agent {", !
    Write "    XData INSTRUCTIONS { ## Contradiction gate ...", !
    Write "      1. Call CheckProtocolContradictions", !
    Write "      2. If BLOCKED: do NOT choose ...", !
    Write "    }", !
    Write "  }", !
    Write "  // Gate only works for SDoHAssessment subclasses.", !
    Write "  // Copy-paste to use in another agent.", !

    Write !, "── Approach B: UseSkill ──────────────────────────────", !
    Write "  Set agent = ##class(%AI.Agent).%New(provider)", !
    Write "  agent.UseSkill(""CareConnect.Skill.ContradictionGate"")", !
    Write "  // Done. Gate active. Any agent. One line.", !
    Write "  // INSTRUCTIONS injected from skill XDATA.", !
    Write "  // Tools registered from SDoHToolSet.", !

    Write !, "── The difference ────────────────────────────────────", !
    Write "  Tools execute.   Skills teach.", !
    Write "  Tools are APIs.  Skills are policies.", !
    Write "  Any agent can load any skill.", !
    Write "  The expensive model solved it once.", !
    Write "  Now every agent inherits the answer.", !

    Quit $$$OK
}

// ---------------------------------------------------------------------------
// Run all
// ---------------------------------------------------------------------------

ClassMethod RunAll() As %Status
{
    Write !, "╔══════════════════════════════════════════════════════╗", !
    Write "║  CareConnect Skill Demo — Contradiction Gate          ║", !
    Write "╚══════════════════════════════════════════════════════╝", !
    Write !, "Prerequisite: docker compose --profile ivg up -d", !, !

    Set sc = ..CompareApproaches()
    If $$$ISERR(sc) Quit sc

    Write !, !
    Set sc = ..SkillDemo()
    If $$$ISERR(sc) Quit sc

    Write !, !
    Write "╔══════════════════════════════════════════════════════╗", !
    Write "║  Key takeaway: UseSkill = portable governance        ║", !
    Write "╚══════════════════════════════════════════════════════╝", !

    Quit $$$OK
}

}
