/// Test double for Sample.AI.OAuth.RoleDiscovery.
/// Overrides GetCallerRoles() to return a configurable value,
/// enabling deterministic filter tests without manipulating $Roles.
Class Test.MockRoleDiscovery Extends Sample.AI.OAuth.RoleDiscovery
{

/// Role string returned by GetCallerRoles(). Set before calling %Resolve().
Property MockRoles As %String [ InitialExpression = "" ];

Method GetCallerRoles() As %String [ Private ]
{
    Return ..MockRoles
}

}
