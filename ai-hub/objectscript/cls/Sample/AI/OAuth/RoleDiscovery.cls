/// Per-session tool catalog filter for OAuth2 role-based access.
///
/// Filters the visible tool catalog to the tools the caller's roles permit.
/// Unauthenticated callers (empty $Roles) see zero role-gated tools.
/// Callers with the %All role see the full catalog.
///
/// Wire this class into a ToolSet via the XML spec:
///   <Policies>
///     <Discovery Class="Sample.AI.OAuth.RoleDiscovery"/>
///   </Policies>
///
/// Two signature details are easy to get wrong, and both were wrong in the
/// first version of this class. The hook is named %Resolve, with the percent
/// sign — a method called Resolve() compiles cleanly and is simply never
/// called. And %Resolve returns %Status, not the catalog: the array is
/// modified in place, so filtering means %Remove() on the array you were
/// handed, not building and returning a new one. Measured on 2026.3.0AI
/// build 139U; see the README's build notes.
Class Sample.AI.OAuth.RoleDiscovery Extends %AI.Policy.Discovery
{

/// Remove tools the caller's roles do not permit from the catalog.
/// catalog is the full %DynamicArray of tool descriptors, modified in place.
/// Returns $$$OK; an error status makes the framework fall back to the
/// unfiltered catalog, which is the opposite of what a role filter wants.
Method %Resolve(catalog As %DynamicArray) As %Status
{
    Set tSC = $$$OK
    Set tRoles = ..GetCallerRoles()

    // %All role — leave the catalog unfiltered
    If tRoles [ "%All" { Return tSC }

    // Walk backwards: %Remove() reindexes everything after the removed slot.
    For i = (catalog.%Size() - 1):-1:0 {
        Set tTool = catalog.%Get(i)
        If '$IsObject(tTool) { Continue }
        Set tMeta = tTool.%Get("metadata")
        // No metadata means no role restriction — always visible
        If '$IsObject(tMeta) { Continue }
        Set tRequired = tMeta.%Get("Role", "")
        If tRequired = "" { Continue }
        If tRoles [ tRequired { Continue }
        Do catalog.%Remove(i)
    }
    Return tSC
}

/// Returns the effective roles for the current request.
/// Override in a subclass to inject roles for testing.
Method GetCallerRoles() As %String [ Private ]
{
    Return $Roles
}

}
