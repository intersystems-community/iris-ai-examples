/// MCP service that authenticates callers with an OAuth2 bearer token and
/// gives each one only the roles its token's scopes map to.
///
/// The whole example is four moving parts:
///
///   1. %AI.MCP.Service.OnAuthenticate — the hook below. Every MCP request
///      passes through it, including tool discovery.
///   2. OAuth2.ResourceServer.ValidateConnection — validates the JWT against
///      the IdP's keys, audience and issuer.
///   3. Sample.AI.OAuth.ScopeAuthenticator — translates the token's scopes
///      into IRIS role names.
///   4. Sample.AI.OAuth.RoleDiscovery / RBACPolicy — filter the tool catalog
///      and gate execution on those roles.
///
/// Setup (one time):
///
///   1. Create your OAuth2.ServerDefinition and OAuth2.ResourceServer records.
///      (Or run Sample.AI.OAuth.Setup.CreateSkeleton() to scaffold them.)
///
///   2. Register the endpoint, the roles and the web application:
///        Do ##class(Sample.AI.OAuth.OAuthMCPService).SetupService()
///
///   3. Verify prerequisites:
///        Do ##class(Sample.AI.OAuth.OAuthMCPService).VerifyPrerequisites()
///
///   4. Point iris-mcp-server at the endpoint. Configure no endpoint-level
///      credentials there: the client's own Authorization: Bearer header is
///      what this service reads.
///
/// To adapt for a different ToolSet or Resource Server name, subclass:
///
///   Class My.OAuthService Extends Sample.AI.OAuth.OAuthMCPService
///   {
///       Parameter SPECIFICATION = "My.ToolSet";
///       Parameter ResourceServerName = "MyResourceServer";
///       Parameter ServicePath = "/mcp/myservice";
///   }
///
/// Measured end to end on IRISHealth 2026.3.0AI build 139U against Keycloak 26,
/// driving tools/list through iris-mcp-server with a per-tier client-credentials
/// token. One tool per tier, from the live token: mcp.read sees GetStatus,
/// mcp.write sees WriteNote, mcp.admin sees AdminReset.
///
/// Two things about this build are worth knowing before you copy it.
///
/// AutheEnabled does not gate the MCP path in either direction. Set to
/// 67108864 (AutheOAuth2) alone, every request is refused with "Unauthorized:
/// Authentication required" whether it carries a valid token or not. Set to
/// 67108928 (AutheOAuth2 + Unauthenticated), every request is admitted with no
/// token check at all. Neither is the mechanism. OnAuthenticate is, so this
/// class registers the application with AutheEnabled = 96 and does the checking
/// itself.
///
/// Type = 19 on the web application is load-bearing (16 MCP + 2 CSP + 1). At
/// Type = 18 the endpoint answers and the application's MatchRoles never
/// reaches the MCP session, so the hook has no privilege to validate anything
/// and nothing logs a reason.
Class Sample.AI.OAuth.OAuthMCPService Extends %AI.MCP.Service
{

/// ToolSet class exposed by this endpoint.
Parameter SPECIFICATION As STRING = "Sample.AI.OAuth.DemoToolSet";

/// Name of the OAuth2.ResourceServer record that validates tokens.
/// Override in a subclass to point at a different resource server.
Parameter ResourceServerName As STRING = "SampleOAuth";

/// Web application path this service is registered at.
///
/// This string is used three times and all three have to agree: it is the web
/// application name, it is the Key of the OAuth2.ResourceServer.Mapping, and it
/// is the `info` argument to ValidateConnection below. Override it in a
/// subclass rather than passing a different path to SetupService.
Parameter ServicePath As STRING = "/mcp/sampleoauth";

/// The IRIS service the OAuth2.ResourceServer.Mapping is registered under.
///
/// %Service_WebGateway is the value that works, but not for the reason it
/// looks like: iris-mcp-server reaches IRIS over the superserver, not over
/// HTTP. The service name here is a key into the Mapping table rather than a
/// statement about the transport, and ValidateConnection looks up
/// service||info and then falls back to service||*. %Service_Bindings is not
/// an alternative — for that service the Mapping Key is a namespace, not a
/// path, so creating one raises "#420: Namespace /mcp/... does not exist".
Parameter OAuthServiceName As STRING = "%Service_WebGateway";

/// Role that carries the privilege OnAuthenticate needs in order to validate a
/// token. Granted to the web application, not to any user. See EnsureRoles.
Parameter ValidatorRole As STRING = "SampleOAuthValidator";

/// Validate the caller's bearer token and reduce the session to the roles that
/// token's scopes grant.
///
/// This is the hook that gates an MCP endpoint. Measured on 2026.3.0AI build
/// 139U: it is called on the discovery path as well as on tools/call, it
/// receives authType="Bearer" and auth set to the raw JWT, and before the
/// application's MatchRoles is applied the session is unauthenticated —
/// $Username is "UnknownUser" — so iris-mcp-server's own service login does
/// not leak into it and role filtering downstream is real rather than
/// short-circuited by %All.
///
/// Returning an error status refuses the connection, which is the only safe
/// failure. Returning $$$OK without setting roles authenticates every caller
/// and leaves them whatever the application granted — an empty tool list if
/// you are lucky, and the full one if you granted the tier roles.
ClassMethod OnAuthenticate(
	authType As %String,
	auth As %String) As %Status
{
	Set tSC = $$$OK
	Try {
		If $ZConvert($Get(authType), "L") '= "bearer" {
			Set tSC = $$$ERROR($$$GeneralError, "MCP endpoint " _ ..#ServicePath _ " requires an OAuth2 bearer token")
			Quit
		}

		Set tSC = ..ValidateBearerToken($Get(auth), .tRoles, .tUsername)
		If $$$ISERR(tSC) { Quit }

		// A token that validates but carries no mapped scope is a refusal, not
		// a caller with no tools. The difference matters: an empty catalog
		// looks like a broken endpoint to whoever is holding the token.
		If tRoles = "" {
			Set tSC = $$$ERROR($$$GeneralError, "Token for '" _ tUsername _ "' carries no scope that maps to an IRIS role")
			Quit
		}

		// Replace $Roles rather than adding to it. The application had to grant
		// this session privilege in order to validate the token at all (see
		// EnsureRoles), and keeping that privilege here would hand every tool
		// call more than the token asked for — and, because RoleDiscovery
		// short-circuits on %All, would silently disable the catalog filter
		// this example exists to demonstrate.
		//
		// Assigning $Roles is itself privileged on this build: without
		// %DB_IRISSYS:RW in the validator role the assignment raises <PROTECT>,
		// and that holds whether the assignment adds a role or only removes
		// one.
		Set $Roles = "%DB_" _ $Namespace _ "," _ tRoles
	} Catch ex {
		Set tSC = ex.AsStatus()
	}
	Quit tSC
}

/// Validate one bearer token against the configured Resource Server.
///
/// pRoles is set to the comma-separated IRIS roles the token's scopes map to,
/// as returned by the Authenticator's DetermineRoles through
/// properties("Roles"); pUsername to properties("Username"), which for a
/// client-credentials token is the IdP's service-account subject.
///
/// The %SYS work is in its own method deliberately. OAuth2.ResourceServer is
/// not mapped outside %SYS, so the call has to switch namespace or it raises
/// <CLASS DOES NOT EXIST> — and `New $Namespace` unwinds at method exit, not at
/// the exit of the Try block that set it. An earlier version made the call
/// inline and its Catch handler then ran in %SYS, where the first thing it
/// touched raised an uncaught <PROTECT> and the endpoint answered HTTP 500 with
/// nothing logged.
ClassMethod ValidateBearerToken(
	pToken As %String,
	Output pRoles As %String,
	Output pUsername As %String) As %Status [ Private ]
{
	Set tSC = $$$OK
	Set pRoles = ""
	Set pUsername = ""
	Try {
		Kill tProps
		New $Namespace
		Set $Namespace = "%SYS"

		// ValidateConnection returns a %Status, not a boolean. An early version
		// of this class tested it as 1/0, which treats every rejection as
		// success: an error status is a string that starts with "0".
		Set tSC = ##class(OAuth2.ResourceServer).ValidateConnection(
			..#OAuthServiceName, ..#ServicePath, pToken, .tProps)
		If $$$ISERR(tSC) { Quit }

		Set pRoles = $Get(tProps("Roles"))
		Set pUsername = $Get(tProps("Username"))
	} Catch ex {
		Set tSC = ex.AsStatus()
	}
	Quit tSC
}

/// Create the demo tier roles and the validator role the hook needs.
///
/// The tier roles (SampleReader / SampleWriter / SampleAdmin) hold no
/// resources. They exist to be named: ScopeAuthenticator maps scopes to them
/// and the ToolSet's <Requirement> tags gate on them.
///
/// The validator role is the uncomfortable part of this example and is written
/// out rather than buried. OnAuthenticate runs before the caller has any
/// identity, so the privilege to validate a token has to come from the web
/// application. Measured minimum on 2026.3.0AI build 139U, by bisecting
/// resource by resource:
///
///   %DB_IRISSYS:R        — read the security database. Without it
///                          ValidateConnection raises <PROTECT>.
///   %DB_IRISSYS:RW       — needed only for the `Set $Roles` in
///                          OnAuthenticate, which raises <PROTECT> at :R even
///                          when it is dropping roles rather than adding them.
///   %Admin_Secure:U      — without it ValidateConnection returns
///                          "#822: Access Denied" and names nothing.
///   %Admin_OAuth2_Client:U — without it ValidateConnection raises
///                          <INVALID OREF> inside ValidateAccessToken. A
///                          resource server needs the *client* resource, which
///                          is not obvious from the name.
///
/// Narrower than that did not work: %Manager works and %Developer does not;
/// %DB_IRISSYS:RW with %Admin_Secure but no OAuth2 resource fails, and with an
/// OAuth2 resource but no %Admin_Secure fails. Write access to the security
/// database is real privilege, so read this as "the MCP endpoint is trusted
/// code", not as "this is least privilege".
ClassMethod EnsureRoles() As %Status
{
	Set tSC = $$$OK
	New $Namespace
	Set $Namespace = "%SYS"
	Try {
		Set tTiers = "SampleReader,SampleWriter,SampleAdmin"
		For i = 1:1:$Length(tTiers, ",") {
			Set tRole = $Piece(tTiers, ",", i)
			If ##class(Security.Roles).Exists(tRole) {
				Write "  Role already exists: ", tRole, !
				Continue
			}
			Set tSC = ##class(Security.Roles).Create(tRole, "OAuth2 RBAC demo tier", "")
			If $$$ISERR(tSC) { Quit }
			Write "  Role created: ", tRole, !
		}
		If $$$ISERR(tSC) { Quit }

		Set tRes = "%DB_IRISSYS:RW,%Admin_Secure:U,%Admin_OAuth2_Client:U"
		If ##class(Security.Roles).Exists(..#ValidatorRole) {
			Kill tProps
			Set tProps("Resources") = tRes
			Set tSC = ##class(Security.Roles).Modify(..#ValidatorRole, .tProps)
			Write "  Role updated: ", ..#ValidatorRole, !
		} Else {
			Set tSC = ##class(Security.Roles).Create(
				..#ValidatorRole,
				"Privilege for Sample.AI.OAuth.OAuthMCPService.OnAuthenticate to validate bearer tokens",
				tRes)
			Write "  Role created: ", ..#ValidatorRole, !
		}
		If $$$ISERR(tSC) { Quit }
		Write "  Validator role resources: ", tRes, !
	} Catch ex {
		Set tSC = ex.AsStatus()
		Write "Error creating roles: ", ex.DisplayString(), !
	}
	Quit tSC
}

/// Register a protected MCP endpoint in the current namespace.
///
/// pPath — kept for callers that pass it explicitly, but the path is
///         ..#ServicePath: ValidateConnection is keyed on that parameter, so a
///         path that disagrees with it cannot authenticate. Override the
///         parameter in a subclass instead.
/// pResourceServerName — OAuth2.ResourceServer record name (default: class parameter)
///
/// Safe to call multiple times (idempotent).
ClassMethod SetupService(
	pPath As %String = "",
	pResourceServerName As %String = "") As %Status
{
	Set tSC = $$$OK
	Set tCallerNS = $Namespace
	Try {
		If (pPath '= "") && (pPath '= ..#ServicePath) {
			Set tSC = $$$ERROR($$$GeneralError, "pPath '" _ pPath _ "' does not match the ServicePath parameter '" _ ..#ServicePath _ "' — override the parameter in a subclass instead")
			Write "Error: ", $System.Status.GetErrorText(tSC), !
			Quit
		}
		Set tPath = ..#ServicePath

		Set tSC = ..EnsureRoles()
		If $$$ISERR(tSC) { Quit }

		Set tSC = ..RegisterApplication(tPath, tCallerNS, pResourceServerName)
	} Catch ex {
		Set tSC = ex.AsStatus()
		Write "Error: ", ex.DisplayString(), !
	}
	Quit tSC
}

/// Create or update the web application and its OAuth2.ResourceServer.Mapping.
/// Split out of SetupService so the %SYS namespace switch unwinds on return.
ClassMethod RegisterApplication(
	pPath As %String,
	pNamespace As %String,
	pResourceServerName As %String = "") As %Status [ Private ]
{
	Set tSC = $$$OK
	New $Namespace
	Set $Namespace = "%SYS"
	Try {
		Set tRSName = $Select(pResourceServerName '= "": pResourceServerName,
		                      1: ..#ResourceServerName)

		// Register the web application through Security.Applications. There is no
		// %SYS.REST.AddApplication on 2026.3 — that call raises
		// <METHOD DOES NOT EXIST> at runtime, which the compiler cannot catch.
		Kill tProps
		Set tProps("NameSpace")          = pNamespace
		Set tProps("Enabled")            = 1
		Set tProps("IsNameSpaceDefault") = 0
		Set tProps("DispatchClass")      = $ClassName()
		// AutheEnabled 96 = Unauthenticated (64) + Password (32). OnAuthenticate
		// is the gate on this path; see the class documentation for what the
		// AutheOAuth2 bit does and does not do here.
		Set tProps("AutheEnabled")       = 96
		// Type 19 = MCP (16) + CSP/REST (2) + 1. The 1 bit is what lets
		// MatchRoles reach the MCP session.
		Set tProps("Type")               = 19
		// Application roles, granted to the session before OnAuthenticate runs.
		// There is no Roles property on Security.Applications on this build;
		// MatchRoles with an empty match ("") always applies.
		Set tProps("MatchRoles")         = ":%DB_" _ pNamespace _ ":" _ ..#ValidatorRole
		Set tProps("Recurse")            = 1
		Set tProps("CookiePath")         = pPath _ "/"

		If ##class(Security.Applications).Exists(pPath) {
			Set tSC = ##class(Security.Applications).Modify(pPath, .tProps)
			Write "  Web app updated: ", pPath, " (Type=19, AutheEnabled=96)", !
		} Else {
			Set tSC = ##class(Security.Applications).Create(pPath, .tProps)
			Write "  Web app registered: ", pPath, " (Type=19, AutheEnabled=96)", !
		}
		If $$$ISERR(tSC) {
			Write "Error registering web app: ", $System.Status.GetErrorText(tSC), !
			Quit
		}
		Write "  Application roles: ", tProps("MatchRoles"), !

		// Wire OAuth2.ResourceServer.Mapping for the service + path
		Set tRSRef = ##class(OAuth2.ResourceServer).%OpenId(tRSName)
		If '$IsObject(tRSRef) {
			Write "  WARNING: OAuth2.ResourceServer '", tRSName, "' not found.", !
			Write "  Run Setup.CreateSkeleton() then fill in IdP values.", !
		} Else {
			If ##class(OAuth2.ResourceServer.Mapping).Exists(..#OAuthServiceName, pPath) {
				Set tSC = ##class(OAuth2.ResourceServer.Mapping).Modify(
					..#OAuthServiceName, pPath, tRSRef)
				Write "  ResourceServer.Mapping updated: ", ..#OAuthServiceName, " / ", pPath, !
			} Else {
				Set tSC = ##class(OAuth2.ResourceServer.Mapping).Create(
					..#OAuthServiceName, pPath, tRSRef)
				Write "  ResourceServer.Mapping created: ", ..#OAuthServiceName, " / ", pPath, !
			}
			If $$$ISERR(tSC) {
				Write "  Mapping error: ", $System.Status.GetErrorText(tSC), !
				Quit
			}
		}
		Write "  Resource Server: ", tRSName, !
		Write "  Endpoint ready at MCP path ", pPath, !
	} Catch ex {
		Set tSC = ex.AsStatus()
		Write "Error: ", ex.DisplayString(), !
	}
	Quit tSC
}

/// Verify that all required OAuth2 records exist before calling SetupService.
///
/// Checks:
///   - OAuth2.ServerDefinition (at least one record)
///   - OAuth2.ResourceServer with the given name
///   - Authenticator.Implementation is non-empty
///   - OAuth2.ResourceServer.Mapping for the service + path
///   - the validator role exists and carries the resources OnAuthenticate needs
///   - the web application is Type 19 and grants the validator role
///
/// Prints a diagnostic line per check. Lines prefixed "FAIL:" indicate missing items.
/// Returns $$$OK if all checks pass, $$$ERROR if any fail.
ClassMethod VerifyPrerequisites(
	pResourceServerName As %String = "",
	pPath As %String = "") As %Status
{
	Set tSC = $$$OK
	Set tAnyFail = 0
	New $Namespace
	Set $Namespace = "%SYS"
	Try {
		Set tRSName = $Select(pResourceServerName '= "": pResourceServerName,
		                      1: ..#ResourceServerName)
		Set tPath = $Select(pPath '= "": pPath, 1: ..#ServicePath)
		Write "Verifying prerequisites for '", tRSName, "' on path '", tPath, "':", !

		// Check OAuth2.ServerDefinition
		&sql(SELECT COUNT(*) INTO :tSrvCount FROM OAuth2.ServerDefinition)
		If SQLCODE = 0 && tSrvCount > 0 {
			Write "  OK: OAuth2.ServerDefinition — ", tSrvCount, " record(s) found", !
		} Else {
			Write "  FAIL: No OAuth2.ServerDefinition records found.", !
			Write "        Create one pointing to your IdP's JWKS endpoint.", !
			Set tAnyFail = 1
		}

		// Check OAuth2.ResourceServer
		&sql(SELECT ID INTO :tRSId FROM OAuth2.ResourceServer WHERE Name = :tRSName)
		If SQLCODE = 0 {
			Write "  OK: OAuth2.ResourceServer '", tRSName, "' found", !
			Set tRSRef = ##class(OAuth2.ResourceServer).%OpenId(tRSId)
			If $IsObject(tRSRef) {
				// Check Authenticator
				Set tImpl = ""
				If $IsObject(tRSRef.Authenticator) {
					Set tImpl = tRSRef.Authenticator.Implementation
				}
				If tImpl '= "" {
					Write "  OK: Authenticator.Implementation = ", tImpl, !
				} Else {
					Write "  FAIL: Authenticator.Implementation is empty.", !
					Write "        Set it to a class that maps JWT claims to role names.", !
					Set tAnyFail = 1
				}
			}
		} Else {
			Write "  FAIL: OAuth2.ResourceServer '", tRSName, "' not found.", !
			Write "        Run Setup.CreateSkeleton() to scaffold it.", !
			Set tAnyFail = 1
		}

		// Check Mapping
		Set tService = ..#OAuthServiceName
		&sql(SELECT ID INTO :tMapId FROM OAuth2_ResourceServer.Mapping
		     WHERE Service = :tService AND Key = :tPath)
		If SQLCODE = 0 {
			Write "  OK: OAuth2.ResourceServer.Mapping found for ", tPath, !
		} Else {
			Write "  FAIL: No ResourceServer.Mapping for ", tService, " / ", tPath, !
			Write "        Run SetupService() to create it.", !
			Set tAnyFail = 1
		}

		// Check the validator role — without it OnAuthenticate cannot validate
		If ##class(Security.Roles).Exists(..#ValidatorRole) {
			Kill tRoleProps
			Do ##class(Security.Roles).Get(..#ValidatorRole, .tRoleProps)
			Set tRoleRes = $Get(tRoleProps("Resources"))
			Set tMissing = ""
			For i = 1:1:3 {
				Set tNeed = $Piece("%DB_IRISSYS:RW,%Admin_Secure:U,%Admin_OAuth2_Client:U", ",", i)
				If '(tRoleRes [ tNeed) { Set tMissing = tMissing _ $Select(tMissing="": "", 1: ", ") _ tNeed }
			}
			If tMissing = "" {
				Write "  OK: Role ", ..#ValidatorRole, " carries the validation resources", !
			} Else {
				Write "  FAIL: Role ", ..#ValidatorRole, " is missing: ", tMissing, !
				Write "        Run EnsureRoles() to repair it.", !
				Set tAnyFail = 1
			}
		} Else {
			Write "  FAIL: Role ", ..#ValidatorRole, " does not exist.", !
			Write "        Run EnsureRoles() to create it.", !
			Set tAnyFail = 1
		}

		// Check the web application's Type and MatchRoles
		If ##class(Security.Applications).Exists(tPath) {
			Kill tAppProps
			Do ##class(Security.Applications).Get(tPath, .tAppProps)
			Set tType = +$Get(tAppProps("Type"))
			// Bit test by arithmetic. $ZBoolean works on character strings, not
			// on integers, so it is the wrong tool for reading a bitmask.
			Set tHasMCP = (tType \ 16) # 2
			Set tHasMatch = tType # 2
			If tHasMCP && tHasMatch {
				Write "  OK: Web app ", tPath, " Type = ", tType, " (MCP + MatchRoles bit set)", !
			} Else {
				Write "  FAIL: Web app ", tPath, " Type = ", tType, " — needs 19 (MCP 16 + CSP 2 + 1).", !
				Write "        At Type 18 the application's roles never reach the MCP session.", !
				Set tAnyFail = 1
			}
			If $Get(tAppProps("MatchRoles")) [ ..#ValidatorRole {
				Write "  OK: Web app grants ", ..#ValidatorRole, !
			} Else {
				Write "  FAIL: Web app MatchRoles does not grant ", ..#ValidatorRole, !
				Write "        Run SetupService() to repair it.", !
				Set tAnyFail = 1
			}
		} Else {
			Write "  FAIL: Web application ", tPath, " does not exist.", !
			Write "        Run SetupService() to create it.", !
			Set tAnyFail = 1
		}

		If 'tAnyFail {
			Write "All prerequisites met.", !
		} Else {
			Set tSC = $$$ERROR($$$GeneralError, "One or more prerequisites missing — see output above")
		}
	} Catch ex {
		Set tSC = ex.AsStatus()
		Write "Error during verification: ", ex.DisplayString(), !
	}
	Quit tSC
}

}
