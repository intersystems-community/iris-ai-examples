/// Demonstration ToolSet for the OAuth2 RBAC example.
///
/// Three stub tools gated at distinct role tiers:
///
///   GetStatus   — requires SampleReader
///   WriteNote   — requires SampleWriter
///   AdminReset  — requires SampleAdmin
///
/// Role requirements are declared in the ToolSet XML spec via <Requirement> tags.
/// The RBACPolicy and RoleDiscovery classes read these tags at enforcement time —
/// no role-to-tool mappings are hardcoded in policy code.
///
/// The <Audit> policy is wired to Sample.AI.Policies.OTelAuditPolicy, whose default
/// exporter POSTs to http://localhost:4318/v1/traces. With no collector listening the
/// POST is refused immediately rather than waiting out its timeout, so leaving it
/// attached costs nothing measurable — verified on 2026.3.0AI build 139U.
///
/// With a SampleReader token:   tools/list returns [GetStatus]
/// With a SampleWriter token:   tools/list returns [WriteNote]
/// With a SampleAdmin token:    tools/list returns [AdminReset]
///
/// All three measured against Keycloak 26 on 2026.3.0AI build 139U.
///
/// A caller with no token, an invalid token, or a valid token carrying no mapped
/// scope does not get an empty tool list — OAuthMCPService.OnAuthenticate refuses
/// the connection, and the endpoint contributes nothing to the catalog. An empty
/// list is indistinguishable from a broken endpoint, so it is a bad way to say
/// "denied".
///
/// Roles are not hierarchical in this example. Grant multiple IRIS roles
/// (e.g., SampleReader + SampleWriter) to expose multiple tiers.
///
/// This ToolSet is registered by Sample.AI.OAuth.OAuthMCPService.
/// Tool implementations return stub strings — replace with real logic to adapt.
///
/// A tool is declared with <Tool Name="..." Method="..."> and its role gate with a
/// nested <Requirement>. Nothing else enumerates. An earlier version of this file
/// wrote <Include Class="..." Match="^GetStatus$"> instead, on the assumption that
/// the spec took regex includes; the class compiled, the MCP endpoint registered,
/// and %Discover() returned {"tools":[]} — the whole example silently exposed
/// nothing, with no error at compile time and none at discovery time. Measured on
/// 2026.3.0AI build 139U.
Class Sample.AI.OAuth.DemoToolSet Extends %AI.ToolSet
{

XData Definition [ MimeType = application/xml ]
{
<ToolSet Name="DemoToolSet">
  <Description>OAuth2 RBAC demo — three tools at Reader, Writer, and Admin tiers.</Description>

  <Policies>
    <Authorization Class="Sample.AI.OAuth.RBACPolicy"/>
    <Discovery Class="Sample.AI.OAuth.RoleDiscovery"/>
    <Audit Class="Sample.AI.Policies.OTelAuditPolicy"/>
  </Policies>

  <Tool Name="GetStatus" Method="GetStatus">
    <Description>Return a stub system status string. Requires the SampleReader role.</Description>
    <Requirement Name="Role" Value="SampleReader"/>
  </Tool>

  <Tool Name="WriteNote" Method="WriteNote">
    <Description>Record a note and return a confirmation. Requires the SampleWriter role.</Description>
    <Requirement Name="Role" Value="SampleWriter"/>
  </Tool>

  <Tool Name="AdminReset" Method="AdminReset">
    <Description>Trigger a stub admin reset. Requires the SampleAdmin role.</Description>
    <Requirement Name="Role" Value="SampleAdmin"/>
  </Tool>

</ToolSet>
}

/// Return a stub system status string.
/// Accessible to callers with the SampleReader role.
ClassMethod GetStatus() As %String
{
    Return "Status: OK — system nominal"
}

/// Record a note and return a confirmation string.
/// Accessible to callers with the SampleWriter role.
ClassMethod WriteNote(pNote As %String) As %String
{
    Return "Note recorded: " _ pNote
}

/// Trigger a stub admin reset and return a confirmation string.
/// Accessible to callers with the SampleAdmin role.
ClassMethod AdminReset() As %String
{
    Return "Admin reset initiated — stub response"
}

}
