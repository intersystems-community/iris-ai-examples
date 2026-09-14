/// Maps OAuth2 scopes in a validated JWT to IRIS roles.
///
/// Wire it into the Resource Server (see Sample.AI.OAuth.Setup):
///   Set tRS = ##class(OAuth2.ResourceServer).%OpenId("SampleOAuth")
///   Set tAuth = {"Implementation":"Sample.AI.OAuth.ScopeAuthenticator",
///                "Namespace":"USER","UserClaim":"sub","RoleClaim":"scope"}
///   Set tRS.Authenticator = tAuth
///   Do tRS.%Save()
///
/// Three things about this hook are easy to get wrong, and the first version of
/// this class got all three wrong. Measured on 2026.3.0AI build 139U.
///
/// 1. A custom authenticator MUST extend %OAuth2.ResourceServer.Authenticator
///    (or a subclass of it). OAuth2.ResourceServer.AuthenticatorSet builds the
///    instance with $classmethod(val.Implementation, "%New", val) and then calls
///    Serialize() on it, so a plain %RegisteredObject fails at %Save() time with
///    <ILLEGAL VALUE> out of GetInstance — not at compile time, and not with any
///    error that names the superclass.
///
/// 2. Roles are returned through the properties array, not by mutating the
///    session. The framework's entry point is
///    Authenticate(claims, oidc, .properties), and it reads properties("Roles")
///    and properties("Username"). Calling %SYS.Session.AddRoles() from here does
///    not do what the name suggests.
///
/// 3. Most of this is already shipped. %OAuth2.ResourceServer.SimpleAuthenticator
///    implements Authenticate(), reads the username out of UserClaim, and splits
///    RoleClaim on spaces with an optional Prefix filter. If your IdP emits role
///    names that are already IRIS role names, configure that class and write no
///    ObjectScript at all. This subclass exists for the common case where it
///    does not: the scope strings ("mcp.read") and the role names
///    ("SampleReader") are different vocabularies, and something has to
///    translate.
Class Sample.AI.OAuth.ScopeAuthenticator Extends %OAuth2.ResourceServer.SimpleAuthenticator
{

/// Scope name → IRIS role. Comma-separated pairs of scope=role.
/// Override in a subclass to retarget at your IdP's scope names.
Parameter SCOPEMAP As STRING = "mcp.read=SampleReader,mcp.write=SampleWriter,mcp.admin=SampleAdmin";

/// Translate the scope claim into IRIS role names.
///
/// The signature is inherited untyped from SimpleAuthenticator — do not add a
/// type to claims, it is a signature mismatch. IRIS calls this only after the
/// access token's signature, issuer and audience have been validated, so the
/// claims are trustworthy.
///
/// Returns a comma-separated role list, or "" to grant no roles. Returning ""
/// is not an error: the caller authenticates as a user with no privileges, and
/// RBACPolicy / RoleDiscovery then show it no role-gated tools.
Method DetermineRoles(claims) As %String
{
    Set tRoles = ""
    If '$IsObject(claims) { Return "" }

    // The scope claim is a space-delimited string in every IdP we have tried
    // (Keycloak, Cognito, Entra). Read it through i%RoleClaim so the mapping
    // still works if the claim is configured to a different name.
    Set tClaimName = $Select(i%RoleClaim'="": i%RoleClaim, 1: "scope")
    Set tScope = ..ScopeString(claims.%Get(tClaimName))
    If tScope = "" { Return "" }

    For i = 1:1:$Length(..#SCOPEMAP, ",") {
        Set tPair = $Piece(..#SCOPEMAP, ",", i)
        Set tScopeName = $Piece(tPair, "=", 1)
        Set tRole = $Piece(tPair, "=", 2)
        Continue:(tScopeName="")||(tRole="")
        If ..ScopeGranted(tScope, tScopeName) {
            Set tRoles = tRoles _ $Select(tRoles="": "", 1: ",") _ tRole
        }
    }
    Return tRoles
}

/// Normalize a scope claim to a space-delimited string.
///
/// Keycloak, Cognito and Entra all emit `scope` as a single space-delimited
/// string, but the claim is allowed to be a JSON array and some IdPs emit one,
/// so accept both rather than silently granting nothing.
ClassMethod ScopeString(pClaim) As %String
{
    If '$IsObject(pClaim) { Return pClaim }
    Set tOut = ""
    Set tIter = pClaim.%GetIterator()
    While tIter.%GetNext(, .tVal) {
        Continue:tVal=""
        Set tOut = tOut _ $Select(tOut="": "", 1: " ") _ tVal
    }
    Return tOut
}

/// Is pScopeName one of the space-delimited entries in pScope?
///
/// Whole-token comparison, deliberately. A substring test ([) would let the
/// scope "mcp.read.denied" grant SampleReader, and would make "mcp.admin"
/// impossible to distinguish from "no.mcp.admin".
ClassMethod ScopeGranted(pScope As %String, pScopeName As %String) As %Boolean
{
    For i = 1:1:$Length(pScope, " ") {
        If $Piece(pScope, " ", i) = pScopeName { Return 1 }
    }
    Return 0
}

}
