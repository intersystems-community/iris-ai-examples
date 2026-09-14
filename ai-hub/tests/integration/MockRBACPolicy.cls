/// Test double for Sample.AI.OAuth.RBACPolicy.
/// Overrides GetCallerRoles() to return a configurable value,
/// enabling deterministic deny/allow tests without manipulating $Roles.
Class Test.MockRBACPolicy Extends Sample.AI.OAuth.RBACPolicy
{

/// Role string returned by GetCallerRoles(). Set before calling %CanExecute/%CanList.
Property MockRoles As %String [ InitialExpression = "" ];

Method GetCallerRoles() As %String [ Private ]
{
    Return ..MockRoles
}

}
