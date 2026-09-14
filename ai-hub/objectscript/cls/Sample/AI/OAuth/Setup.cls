/// Setup utilities for the OAuth2 RBAC example.
///
/// Use these methods to scaffold the required OAuth2 records before calling
/// OAuthMCPService.SetupService().
///
/// Quick start:
///   1. Do ##class(Sample.AI.OAuth.Setup).CreateSkeleton()
///   2. Fill in the fields printed by the checklist (IdP issuer, JWKS, authenticator)
///   3. Do ##class(Sample.AI.OAuth.OAuthMCPService).SetupService("/api/oauth/mcp")
///   4. Do ##class(Sample.AI.OAuth.OAuthMCPService).VerifyPrerequisites()
Class Sample.AI.OAuth.Setup Extends %RegisteredObject
{

/// Scaffold placeholder OAuth2 records and print a setup checklist.
///
/// Creates (if absent):
///   - OAuth2.ServerDefinition with IssuerEndpoint = "https://YOUR-IDP/"
///   - OAuth2.ResourceServer named pResourceServerName with empty Authenticator
///
/// Safe to call multiple times (idempotent).
ClassMethod CreateSkeleton(pResourceServerName As %String = "SampleOAuth") As %Status
{
    Set tSC = $$$OK
    New $namespace
    Set $namespace = "%SYS"
    Try {
        Set tPlaceholderIssuer = "https://YOUR-IDP/"

        // Create placeholder ServerDefinition if none exists with placeholder issuer
        &sql(SELECT COUNT(*) INTO :tCount FROM OAuth2.ServerDefinition
             WHERE IssuerEndpoint = :tPlaceholderIssuer)
        If SQLCODE '= 0 || tCount = 0 {
            Set tSrv = ##class(OAuth2.ServerDefinition).%New()
            Set tSrv.IssuerEndpoint = tPlaceholderIssuer
            Set tSC2 = tSrv.%Save()
            If $$$ISERR(tSC2) {
                Write "  Warning: could not create ServerDefinition placeholder: ",
                      $System.Status.GetErrorText(tSC2), !
            } Else {
                Write "  Created OAuth2.ServerDefinition (placeholder)", !
            }
        } Else {
            Write "  OAuth2.ServerDefinition placeholder already exists", !
        }

        // Create ResourceServer if absent
        &sql(SELECT ID INTO :tRSId FROM OAuth2.ResourceServer WHERE Name = :pResourceServerName)
        If SQLCODE '= 0 {
            Kill tProps
            Set tProps("AccessTokenIsJWT") = 1
            Set tProps("ServerDefinition")  = tPlaceholderIssuer
            Set tProps("Audiences")         = "YOUR-CLIENT-ID"
            Set tAuthObj = {}
            Set tAuthObj.Implementation = ""
            Set tAuthObj.Namespace = $Namespace
            Set tProps("Authenticator") = tAuthObj
            Set tSC2 = ##class(OAuth2.ResourceServer).Create(pResourceServerName, .tProps)
            If $$$ISERR(tSC2) {
                Write "  Warning: could not create ResourceServer: ",
                      $System.Status.GetErrorText(tSC2), !
            } Else {
                Write "  Created OAuth2.ResourceServer '", pResourceServerName, "' (placeholder)", !
            }
        } Else {
            Write "  OAuth2.ResourceServer '", pResourceServerName, "' already exists", !
        }

        Write !
        Do ..PrintChecklist(pResourceServerName)
        Write !
        Write "Skeleton ready. Fill in the fields above, then run:", !
        Write "  Do ##class(Sample.AI.OAuth.OAuthMCPService).SetupService(""/api/oauth/mcp"")", !
    } Catch ex {
        Set tSC = ex.AsStatus()
        Write "Error: ", ex.DisplayString(), !
    }
    Return tSC
}

/// Print a checklist of fields to fill in before the example will work.
/// Does not create or modify any records.
ClassMethod PrintChecklist(pResourceServerName As %String = "SampleOAuth") As %Status
{
    Set tSC = $$$OK
    Write "OAuth2 RBAC Example — Setup Checklist", !
    Write "======================================", !
    Write !
    Write "Resource Server name: ", pResourceServerName, !
    Write !
    Write "Required fields to fill in:", !
    Write !
    Write "  1. OAuth2.ServerDefinition.IssuerEndpoint", !
    Write "     Your IdP's issuer URL, e.g.:", !
    Write "       https://cognito-idp.us-east-1.amazonaws.com/us-east-1_XXXXXXX", !
    Write "       https://YOUR-TENANT.auth0.com/", !
    Write !
    Write "  2. OAuth2.ServerDefinition public JWKS", !
    Write "     Fetch from your IdP's /.well-known/jwks.json endpoint and", !
    Write "     store in OAuth2.ServerDefinition.PublicJWKS (JSON string).", !
    Write !
    Write "  3. OAuth2.ResourceServer '", pResourceServerName, "'.Authenticator.Implementation", !
    Write "     Sample.AI.OAuth.ScopeAuthenticator, or your own subclass of", !
    Write "     %OAuth2.ResourceServer.Authenticator. It MUST extend that class —", !
    Write "     a plain %RegisteredObject with a DetermineRoles method fails at", !
    Write "     %Save() time with <ILLEGAL VALUE>, not at compile time.", !
    Write "     Roles come back through properties(""Roles""); do not try to", !
    Write "     mutate the session from inside the authenticator.", !
    Write !
    Write "  4. OAuth2.ResourceServer '", pResourceServerName, "'.Audiences", !
    Write "     Your client ID / audience claim from the IdP.", !
    Write !
    Write "  5. Roles, web application and Resource Server mapping:", !
    Write "       Do ##class(Sample.AI.OAuth.OAuthMCPService).SetupService()", !
    Write "     Creates SampleReader / SampleWriter / SampleAdmin, creates the", !
    Write "     validator role the auth hook needs, and registers the endpoint.", !
    Write "     Idempotent — safe to re-run.", !
    Write !
    Write "  6. Verify:", !
    Write "       Do ##class(Sample.AI.OAuth.OAuthMCPService).VerifyPrerequisites()", !
    Write !
    Return tSC
}

}
