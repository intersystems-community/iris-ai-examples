Include %AI

/// Role-based access control policy for OAuth2-protected MCP endpoints.
///
/// Reads IRIS session roles ($Roles) to gate tool visibility and execution.
/// Roles are injected by the OAuth2 Resource Server authenticator at the CSP
/// layer — this class does not parse JWTs or call any OAuth2 APIs directly.
///
/// Wire this class into a ToolSet via the XML spec:
///   <Policies>
///     <Authorization Class="Sample.AI.OAuth.RBACPolicy"/>
///   </Policies>
///
/// Each tool declares its required role via a <Requirement> tag:
///   <Include Class="My.ToolSet" Match="^ReadTool$">
///     <Requirement Name="Role" Value="SampleReader"/>
///   </Include>
///
/// Tools with no <Requirement> are always accessible.
///
/// Requires IRIS 2026.3+ Build 148+ for catalog filtering (%CanList 2-arg).
/// On older builds, %CanExecute still enforces access.
Class Sample.AI.OAuth.RBACPolicy Extends %AI.Policy.Authorization
{

/// Called by the framework before including a tool in tools/list.
/// metadata contains the tool's <Requirement> values as a %DynamicObject.
/// Requires Build 148+ for the 2-arg signature (metadata passed).
Method %CanList(tool As %String, metadata As %DynamicObject) As %Boolean
{
    Set tRequired = ""
    If $IsObject(metadata) { Set tRequired = metadata.%Get("Role", "") }
    If tRequired = "" { Return 1 }
    Set tRoles = ..GetCallerRoles()
    If tRoles [ "%All" { Return 1 }
    If tRoles [ tRequired { Return 1 }
    Return 0
}

/// Called by the framework before executing a tool call.
/// Provides defense-in-depth — enforces access even if caller bypasses catalog.
Method %CanExecute(tool As %String, call As %DynamicObject, metadata As %DynamicObject) As %Status
{
    Set tSC = $$$OK
    Set tRequired = ""
    If $IsObject(metadata) { Set tRequired = metadata.%Get("Role", "") }
    If tRequired = "" { Return $$$OK }
    Set tRoles = ..GetCallerRoles()
    If tRoles [ "%All" { Return $$$OK }
    If tRoles [ tRequired { Return $$$OK }
    Return $$$ERROR($$$AICoreToolAccessDenied, "Role '" _ tRequired _ "' required to call tool '" _ tool _ "'")
}

/// Returns the effective roles for the current request.
/// Reads $Roles directly — set by the OAuth2 ResourceServer authenticator.
Method GetCallerRoles() As %String [ Private ]
{
    Return $Roles
}

}
