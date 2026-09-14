/// Jira Agent example — AI Hub agent with live Atlassian data via the Rovo MCP Server.
///
/// Demonstrates connecting an %AI.Agent to the official Atlassian Rovo MCP Server
/// (https://mcp.atlassian.com) using bearer-token auth. The agent can search Jira
/// issues, fetch details, add comments, and query Confluence — all via natural language.
///
/// Setup (one-time):
///   1. Create an Atlassian API token:
///        https://id.atlassian.com/manage-profile/security/api-tokens
///
///   2. Set the token in the environment before starting IRIS
///      (must be in the IRIS process environment, not just the shell):
///        export ATLASSIAN_API_TOKEN=<your-api-token>
///      For Docker, pass it at container start:
///        docker run -e ATLASSIAN_API_TOKEN=<token> ...
///
///   3. Set your LLM API key:
///        export OPENAI_API_KEY=sk-...
///
/// Run from the IRIS terminal:
///   Do ##class(Sample.AI.Examples.JiraAgent).Demo()
///   Do ##class(Sample.AI.Examples.JiraAgent).SearchIssues("project = MYPROJ AND assignee = currentUser()")
///   Do ##class(Sample.AI.Examples.JiraAgent).FetchIssue("MYPROJ-123")
///
/// Note: always pass the ToolSet as an instance (##class(...).%New()), not as
/// the "iris:ClassName" string URI — the string form uses a re-entrant callin
/// path that causes a crash on this build.
Class Sample.AI.Examples.JiraAgent Extends %RegisteredObject
{

/// Run an interactive Jira agent session using the Atlassian Rovo MCP Server.
ClassMethod Demo() As %Status
{
    Set tSC = $$$OK
    Try {
        Write !, "=== Jira Agent (Atlassian Rovo MCP Server) ===", !

        Set tToken = $System.Util.GetEnviron("ATLASSIAN_API_TOKEN")
        If tToken = "" {
            Write "Error: ATLASSIAN_API_TOKEN not set.", !
            Write "Create one at https://id.atlassian.com/manage-profile/security/api-tokens", !
            Return $$$ERROR($$$GeneralError, "ATLASSIAN_API_TOKEN not configured")
        }

        Set tApiKey = ##class(Sample.AI.Utils).GetAPIKey("openai")
        If tApiKey = "" {
            Write "Error: OPENAI_API_KEY not set", !
            Return $$$ERROR($$$GeneralError, "Missing API key")
        }

        Set tSettings = {}
        Do tSettings.%Set("api_key", tApiKey)
        Set tProvider = ##class(%AI.Provider).Create("openai", tSettings)

        Set tAgent = ##class(%AI.Agent).%New(tProvider)
        Set tAgent.Model = "gpt-4o"
        Set tAgent.SystemPrompt = "You are an Atlassian assistant with access to live Jira and Confluence data. Use the available tools to answer questions accurately. When listing Jira issues, include the key, summary, status, and assignee. Format output as clean readable text."

        Do tAgent.ToolManager.AddTool(##class(Sample.AI.Tools.JiraTools).%New())
        Write "Atlassian tools loaded (mcp.atlassian.com)", !, !

        Set tSession = tAgent.CreateSession()

        Set tQuestions = $ListBuild(
            "What Jira issues are currently assigned to me?",
            "Are there any high-priority open bugs in my projects?",
            "Summarize the top 3 most recently updated issues."
        )

        Set tPtr = 0
        While $ListNext(tQuestions, tPtr, tQuestion) {
            Write "Q: ", tQuestion, !
            Set tResponse = tAgent.Chat(tSession, tQuestion)
            Write "A: ", tResponse.Content, !, !
        }

    } Catch ex {
        Set tSC = ex.AsStatus()
        Write "Error: ", ex.DisplayString(), !
    }
    Return tSC
}

/// Ask the agent a free-form question about Jira or Confluence.
ClassMethod Ask(pQuestion As %String) As %Status
{
    Set tSC = $$$OK
    Try {
        If $System.Util.GetEnviron("ATLASSIAN_API_TOKEN") = "" {
            Write "ATLASSIAN_API_TOKEN not set — see class comment for setup.", !
            Return $$$ERROR($$$GeneralError, "ATLASSIAN_API_TOKEN not configured")
        }

        Set tApiKey = ##class(Sample.AI.Utils).GetAPIKey("openai")
        If tApiKey = "" {
            Write "OPENAI_API_KEY not set", !
            Return $$$ERROR($$$GeneralError, "Missing API key")
        }

        Set tSettings = {}
        Do tSettings.%Set("api_key", tApiKey)
        Set tProvider = ##class(%AI.Provider).Create("openai", tSettings)

        Set tAgent = ##class(%AI.Agent).%New(tProvider)
        Set tAgent.Model = "gpt-4o"
        Set tAgent.SystemPrompt = "You are an Atlassian assistant. Use tools to answer with live data."
        Do tAgent.ToolManager.AddTool(##class(Sample.AI.Tools.JiraTools).%New())

        Set tSession = tAgent.CreateSession()
        Write "Q: ", pQuestion, !
        Set tResponse = tAgent.Chat(tSession, pQuestion)
        Write "A: ", tResponse.Content, !

    } Catch ex {
        Set tSC = ex.AsStatus()
        Write "Error: ", ex.DisplayString(), !
    }
    Return tSC
}

/// Convenience: search issues by JQL and display results.
/// Example: Do ##class(Sample.AI.Examples.JiraAgent).SearchIssues("assignee = currentUser() AND status != Done")
ClassMethod SearchIssues(pJQL As %String = "assignee = currentUser() ORDER BY updated DESC") As %Status
{
    Return ..Ask("Search Jira using JQL: " _ pJQL _ ". List all results with key, summary, status, and assignee.")
}

/// Convenience: fetch a single issue by key.
/// Example: Do ##class(Sample.AI.Examples.JiraAgent).FetchIssue("PROJ-123")
ClassMethod FetchIssue(pKey As %String) As %Status
{
    Return ..Ask("Fetch Jira issue " _ pKey _ " and show all details: summary, description, status, assignee, priority, and any comments.")
}

}
