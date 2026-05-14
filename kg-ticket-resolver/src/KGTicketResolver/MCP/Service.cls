/// KGTicketResolver MCP Service
///
/// Registers the ToolSet with the AI Hub MCP server endpoint.
Class KGTicketResolver.MCP.Service Extends %AI.MCP.Service
{

Parameter ENDPOINT = "/mcp/kgtickets";

Parameter TOOLSETS = "KGTicketResolver.Tools.ToolSet";

}
