/// ToolSet that connects to the Atlassian Rovo MCP Server.
///
/// The official Atlassian Rovo MCP Server (https://mcp.atlassian.com) is a
/// cloud-hosted bridge that gives AI agents access to Jira, Confluence, Jira
/// Service Management, Bitbucket, and Compass in real time. Authentication
/// uses an Atlassian API token (available from id.atlassian.com).
///
/// Setup (one-time):
///
///   1. Create an Atlassian API token:
///        https://id.atlassian.com/manage-profile/security/api-tokens
///      Name it something like "AI Hub MCP Demo".
///
///   2. Set the token as an environment variable before starting IRIS:
///        export ATLASSIAN_API_TOKEN=<your-api-token>
///
///      Or store it in the AI Hub wallet:
///        Do ##class(%AI.Utils.Wallet).SetSecret("ATLASSIAN_API_TOKEN", "<your-api-token>")
///
///   3. Set your LLM API key:
///        export OPENAI_API_KEY=sk-...
///
/// Run from the IRIS terminal:
///   Do ##class(Sample.AI.Examples.JiraAgent).Demo()
///   Do ##class(Sample.AI.Examples.JiraAgent).SearchIssues("project = MYPROJ AND assignee = currentUser()")
///   Do ##class(Sample.AI.Examples.JiraAgent).FetchIssue("MYPROJ-123")
///
/// Tools exposed (depends on your Atlassian permissions):
///   jira_get_issue          - Fetch an issue by key (fields, comments, status)
///   jira_search             - JQL search returning matching issues
///   jira_create_issue       - Create a new issue
///   jira_update_issue       - Update summary, description, or status
///   jira_add_comment        - Add a comment to an issue
///   jira_get_projects       - List accessible projects
///   jira_get_transitions    - List available status transitions for an issue
///   confluence_search       - Full-text search across Confluence spaces
///   confluence_get_page     - Fetch a Confluence page by ID or title
Class Sample.AI.Tools.JiraTools Extends %AI.ToolSet
{

XData Definition [ MimeType = application/xml ]
{
  <ToolSet Name="JiraTools">
    <Description>Atlassian tools (Jira and Confluence) via the official Atlassian Rovo MCP Server — search and update issues, fetch pages, create content.</Description>

    <MCP Name="atlassian">
      <Remote URL="https://mcp.atlassian.com/v1/mcp/authv2"
              AuthType="bearer"
              Token="@{env:ATLASSIAN_API_TOKEN}"/>
    </MCP>

  </ToolSet>
}

}
