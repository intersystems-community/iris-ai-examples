/// Demo RBAC setup — roles and users used by the CareConnect SDoH agent.
/// Idempotent: safe to run on every container start.
/// Security.* classes only exist in %SYS, so each method switches namespace
/// and restores it on every exit path.
Class CareConnect.Setup.Roles
{

ClassMethod CreateAll() As %Status
{
    Set tSC = $$$OK
    Set tSC = ..CreateRole("chw_role",          "Community Health Worker — read patient data, assess SDoH, draft care plans", ..RW())
    Quit:$$$ISERR(tSC) tSC
    Set tSC = ..CreateRole("chw_senior_role",   "Senior CHW — all CHW capabilities plus trigger follow-up workflows and prior auth", ..RW())
    Quit:$$$ISERR(tSC) tSC
    Set tSC = ..CreateRole("admin_role",        "Administrator — full access including production management", ..RW())
    Quit:$$$ISERR(tSC) tSC
    Set tSC = ..CreateRole("readonly_role",     "Read-only analyst — FHIR readiness check and status only", ..RO())
    Quit:$$$ISERR(tSC) tSC
    Set tSC = ..CreateRole("case_manager_role", "Case Manager — submit and track prior authorization requests", ..RW())
    Quit:$$$ISERR(tSC) tSC
    Set tSC = ..CreateUser("chw_user", "chw_pass",    "chw_role")
    Quit:$$$ISERR(tSC) tSC
    Set tSC = ..CreateUser("chw_sr",   "chw_sr_pass", "chw_senior_role")
    Quit:$$$ISERR(tSC) tSC
    Set tSC = ..CreateUser("ro_user",  "ro_pass",     "readonly_role")
    Quit:$$$ISERR(tSC) tSC
    Set tSC = ..CreateUser("cm_user",  "cm_pass",     "case_manager_role")
    Quit:$$$ISERR(tSC) tSC
    Set tSC = ..GrantTablePrivileges()
    Write "Roles/users ready: ",$System.Status.IsOK(tSC),!
    Quit tSC
}

/// Grant SQL SELECT (and write access for mutating roles) on CareConnect tables.
/// Idempotent — duplicate grants are silently accepted.
ClassMethod GrantTablePrivileges() As %Status
{
    Set tSC = $$$OK
    Set stmt = ##class(%SQL.Statement).%New()
    // Read access: all roles
    For tRole = "chw_role", "chw_senior_role", "readonly_role", "case_manager_role", "admin_role" {
        Set tR = stmt.%ExecDirect(, "GRANT SELECT ON CareConnect.Patient TO " _ tRole)
        // SQLCODE 100 = privilege already granted — idempotent, not an error
        If (tR.%SQLCODE '= 0) && (tR.%SQLCODE '= 100) Write "WARN GRANT Patient->",tRole,": SQLCODE=",tR.%SQLCODE," ",tR.%Message,!
    }
    // Write access: mutating roles only
    For tRole = "chw_role", "chw_senior_role", "admin_role" {
        Set tR = stmt.%ExecDirect(, "GRANT INSERT, UPDATE ON CareConnect.Patient TO " _ tRole)
        If tR.%SQLCODE '= 0 Write "WARN GRANT Patient(W)->",tRole,": SQLCODE=",tR.%SQLCODE," ",tR.%Message,!
    }
    Quit tSC
}

/// Minimum resources for a superserver (DBAPI / Native SDK) login to USER.
/// The bindings service is governed by the %Service_Native/Object/SQL resources;
/// only %Service_SQL and %DB_USER access are not public on this image, so grant all three.
ClassMethod RW() As %String [ CodeMode = expression ]
{
"%DB_USER:RW,%Service_Native:U,%Service_Object:U,%Service_SQL:U"
}

ClassMethod RO() As %String [ CodeMode = expression ]
{
"%DB_USER:R,%Service_Native:U,%Service_Object:U,%Service_SQL:U"
}

ClassMethod CreateRole(pName As %String, pDescription As %String, pResources As %String) As %Status
{
    Set tSC = $$$OK
    Set tNS = $Namespace
    Try {
        Set $Namespace = "%SYS"
        If ##class(Security.Roles).Exists(pName) {
            // Keep existing roles in sync with the code — resources may have changed
            Set tProps("Description") = pDescription
            Set tProps("Resources") = pResources
            Set tSC = ##class(Security.Roles).Modify(pName, .tProps)
        } Else {
            Set tSC = ##class(Security.Roles).Create(pName, pDescription, pResources)
        }
    } Catch ex {
        Set tSC = ex.AsStatus()
    }
    Set $Namespace = tNS
    If $$$ISERR(tSC) Write "ERROR creating role ",pName,": ",$System.Status.GetErrorText(tSC),!
    Quit tSC
}

ClassMethod CreateUser(pUsername As %String, pPassword As %String, pRole As %String) As %Status
{
    Set tSC = $$$OK
    Set tNS = $Namespace
    Try {
        Set $Namespace = "%SYS"
        If '##class(Security.Users).Exists(pUsername) {
            // Create(Username, UserRoles, Password, FullName, NameSpace, Routine, ExpirationDate,
            //        ChangePassword, Enabled, Comment, Flags, PhoneNumber, PhoneProvider,
            //        &Attributes, AccountNeverExpires, PasswordNeverExpires, ...)
            Set tSC = ##class(Security.Users).Create(pUsername, pRole, pPassword, pUsername, "USER", "", "", 0, 1, "CareConnect demo user", , , , , 1, 1)
        }
    } Catch ex {
        Set tSC = ex.AsStatus()
    }
    Set $Namespace = tNS
    If $$$ISERR(tSC) Write "ERROR creating user ",pUsername,": ",$System.Status.GetErrorText(tSC),!
    Quit tSC
}

}
