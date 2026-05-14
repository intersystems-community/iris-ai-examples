Include %AI

/// CareConnect SDoH ToolSet
///
/// Exposes social determinants of health (SDoH) tools via the AI Hub MCP server.
/// Demo patient data lives in the CareConnect.Patient SQL table — no FHIR dependency.
///
/// Tools exposed:
///   SearchPatients          — list/search the demo patient roster
///   FetchPatientSummary     — get clinical summary for a patient
///   SearchSDoHProtocols     — find screening protocols matching conditions
///   AssessSDoHRisk          — score all 5 USDHHS SDoH domains
///   DraftCarePlan           — generate an actionable care plan
///   TriggerFollowUp         — fire the Interoperability follow-up workflow
///   GetInteropTraces        — view recent message flow from the production
///   GetProductionStatus     — check whether the production is running
///   StartProduction         — start CareConnect.Production
Class CareConnect.Tools.SDoHToolSet Extends %AI.ToolSet [DependsOn = CareConnect.Tools.SDoHToolSet]
{

XData Definition
{
<ToolSet>
  <Description>CareConnect SDoH Tools — patient lookup, risk assessment, care planning, interop tracing</Description>
  <Include Class="CareConnect.Tools.SDoHToolSet"/>

  <Tool Name="SearchPatients" Method="SearchPatients">
    <Description>List all demo patients or search by name, condition, or patient ID. Returns patientId values for use with FetchPatientSummary.</Description>
  </Tool>

  <Tool Name="FetchPatientSummary" Method="FetchPatientSummary">
    <Description>Fetch clinical conditions, observations, and social context for a patient from the demo database.</Description>
  </Tool>

  <Tool Name="SearchSDoHProtocols" Method="SearchSDoHProtocols">
    <Description>Search the SDoH protocol knowledge base for screening guidelines that match the patient conditions.</Description>
  </Tool>

  <Tool Name="AssessSDoHRisk" Method="AssessSDoHRisk">
    <Description>Score a patient on all five USDHHS SDoH domains using clinical summary and matched protocols.</Description>
  </Tool>

  <Tool Name="DraftCarePlan" Method="DraftCarePlan">
    <Description>Draft an actionable care plan with prioritized steps for the community health worker based on SDoH risk scores.</Description>
  </Tool>

  <Tool Name="TriggerFollowUp" Method="TriggerFollowUp">
    <Description>Trigger an SDoH follow-up workflow via the IRIS Interoperability production.</Description>
  </Tool>

  <Tool Name="GetInteropTraces" Method="GetInteropTraces">
    <Description>Show recent IRIS Interoperability message traces: source, target, message class, status, and timestamp.</Description>
  </Tool>

  <Tool Name="GetProductionStatus" Method="GetProductionStatus">
    <Description>Get the current status of the CareConnect IRIS Interoperability production and list active components.</Description>
  </Tool>

  <Tool Name="StartProduction" Method="StartProduction">
    <Description>Start the CareConnect IRIS Interoperability production. Safe to call if already running.</Description>
  </Tool>

</ToolSet>
}

ClassMethod SearchPatients(query As %String = "") As %String
{
    Set q = $ZCONVERT(query, "L")
    Set stmt = ##class(%SQL.Statement).%New()
    If q = "" {
        Set sc = stmt.%Prepare("SELECT PatientId, Name, Demographics, Conditions, SDoHFlags FROM CareConnect.Patient ORDER BY Name")
        Set rs = stmt.%Execute()
        Set out = "Available patients (use patientId with FetchPatientSummary):"_$Char(10)
        While rs.%Next() {
            Set out = out_"  "_rs.PatientId_" | "_rs.Name_" | "_rs.Demographics_" | "_rs.Conditions_$Char(10)
        }
        If rs.%ROWCOUNT = 0 Quit "No patients in database. Run CareConnect.Setup.DemoData.Load() to seed demo patients."
        Quit out
    }
    Set sc = stmt.%Prepare("SELECT PatientId, Name, Demographics, Conditions, SDoHFlags, Notes FROM CareConnect.Patient WHERE LOWER(Name) LIKE ? OR LOWER(Conditions) LIKE ? OR PatientId = ?")
    Set pat = "%"_q_"%"
    Set rs = stmt.%Execute(pat, pat, query)
    Set out = ""
    While rs.%Next() {
        Set out = out_"patientId: "_rs.PatientId_$Char(10)
        Set out = out_"  Name: "_rs.Name_$Char(10)
        Set out = out_"  Demographics: "_rs.Demographics_$Char(10)
        Set out = out_"  Conditions: "_rs.Conditions_$Char(10)
        Set out = out_"  SDoH flags: "_rs.SDoHFlags_$Char(10,10)
    }
    If out = "" Quit "No patients found matching '"_query_"'. Call SearchPatients with no arguments to list all."
    Quit out
}

ClassMethod FetchPatientSummary(patientId As %String, daysBack As %String = "90") As %String
{
    If patientId = "" Quit "ERROR: patientId is required"
    Set stmt = ##class(%SQL.Statement).%New()
    Set sc = stmt.%Prepare("SELECT Name, Demographics, Conditions, Observations, Notes FROM CareConnect.Patient WHERE PatientId = ?")
    Set rs = stmt.%Execute(patientId)
    If 'rs.%Next() Quit "Patient not found: "_patientId_". Call SearchPatients to list available patients."
    Set out = "Patient: "_rs.Name_", "_rs.Demographics_$Char(10)
    Set conds = rs.Conditions
    Set ptr = 1
    For { Set c = $Piece(conds, "|", ptr) Quit:c=""  Set out = out_"Condition: "_c_$Char(10)  Set ptr = ptr + 1 }
    Set obs = rs.Observations
    Set ptr = 1
    For { Set o = $Piece(obs, "|", ptr) Quit:o=""  Set out = out_"Observation: "_o_$Char(10)  Set ptr = ptr + 1 }
    Set out = out_"Note: "_rs.Notes
    Quit out
}

ClassMethod SearchSDoHProtocols(conditions As %String) As %String
{
    If conditions = "" Quit "ERROR: conditions is required"
    Set condLC = $ZCONVERT(conditions, "L")
    Set out = ""
    If (condLC["diabetes")||(condLC["hba1c")||(condLC["glucose") {
        Set out = out_"Protocol: ADA Diabetes Distress Screening (Problem Areas in Diabetes scale)"_$Char(10)
        Set out = out_"Protocol: Food Insecurity Screening - Hunger Vital Sign 2-item tool"_$Char(10)
        Set out = out_"Protocol: AADE7 Self-Care Behaviors assessment for diabetes management barriers"_$Char(10)
    }
    If (condLC["hypertension")||(condLC["blood pressure") {
        Set out = out_"Protocol: AHA Hypertension Social Needs Screening Tool"_$Char(10)
        Set out = out_"Protocol: Housing Instability Screening - iHELP instrument"_$Char(10)
    }
    If (condLC["heart")||(condLC["chf")||(condLC["bnp") {
        Set out = out_"Protocol: ACC/AHA Social Determinants of Cardiovascular Risk Protocol"_$Char(10)
        Set out = out_"Protocol: Social Isolation and Loneliness Screening - UCLA Loneliness Scale (3-item)"_$Char(10)
    }
    If (condLC["depress")||(condLC["phq")||(condLC["mental") {
        Set out = out_"Protocol: PHQ-9 Depression Screening with SDoH integration workflow"_$Char(10)
        Set out = out_"Protocol: Social Connection and Support Network Assessment"_$Char(10)
    }
    If (condLC["food")||(condLC["nutrition")||(condLC["anemia") {
        Set out = out_"Protocol: USDA Household Food Security Survey Module (2-item screen)"_$Char(10)
        Set out = out_"Protocol: WIC Referral and Community Food Resource Navigation Protocol"_$Char(10)
    }
    If (condLC["housing")||(condLC["transport")||(condLC["financial")||(condLC["uninsured") {
        Set out = out_"Protocol: PRAPARE SDoH Screening Tool"_$Char(10)
        Set out = out_"Protocol: Community Health Worker Navigation Referral Protocol"_$Char(10)
    }
    If out = "" {
        Set out = "Protocol: PRAPARE Universal SDoH Screening Tool"_$Char(10)
        Set out = out_"Protocol: NACHC Social Needs Screening and Referral Workflow"_$Char(10)
    }
    Quit out
}

ClassMethod AssessSDoHRisk(patientId As %String, clinicalSummary As %String, protocolMatches As %String) As %String
{
    If patientId = "" Quit "ERROR: patientId is required"
    Set summaryLC = $ZCONVERT(clinicalSummary, "L")
    Set econ = $Select((summaryLC["unemploy")||(summaryLC["job")||(summaryLC["income")||(summaryLC["afford"):"HIGH", 1:"LOW")
    Set edu = $Select((summaryLC["english")||(summaryLC["language")||(summaryLC["literacy"):"HIGH", 1:"LOW")
    Set health = $Select((summaryLC["uninsur")||(summaryLC["transport")||(summaryLC["no doctor")||(summaryLC["clinic"):"HIGH", 1:"MEDIUM")
    Set nbhd = $Select((summaryLC["housing")||(summaryLC["mold")||(summaryLC["unsafe")||(summaryLC["food bank"):"HIGH", 1:"LOW")
    Set social = $Select((summaryLC["alone")||(summaryLC["isolat")||(summaryLC["no family")||(summaryLC["no support"):"HIGH", 1:"LOW")
    Set out = "SDoH Risk Assessment for "_patientId_":"_$Char(10)
    Set out = out_"  Economic Stability:      "_econ_$Char(10)
    Set out = out_"  Education Access:        "_edu_$Char(10)
    Set out = out_"  Health Care Access:      "_health_$Char(10)
    Set out = out_"  Neighborhood/Built Env:  "_nbhd_$Char(10)
    Set out = out_"  Social Context:          "_social_$Char(10)
    Set highCount = 0
    For d = econ, edu, health, nbhd, social { If d = "HIGH" Set highCount = highCount + 1 }
    Set priority = $Select(highCount >= 4:"URGENT", highCount >= 2:"HIGH", 1:"ROUTINE")
    Set out = out_"Overall Priority: "_priority_" ("_highCount_"/5 domains elevated)"
    Quit out
}

ClassMethod DraftCarePlan(patientId As %String, sdohScores As %String) As %String
{
    If patientId = "" Quit "ERROR: patientId is required"
    Set scoresLC = $ZCONVERT(sdohScores, "L")
    Set out = "Care Plan for "_patientId_":"_$Char(10,10)
    Set step = 1
    If scoresLC["economic" {
        Set out = out_step_". Connect with financial assistance programs — SNAP, Medicaid, emergency rental assistance"_$Char(10)
        Set step = step + 1
    }
    If (scoresLC["health care")||(scoresLC["transport") {
        Set out = out_step_". Schedule CHW home visit within 5 days — assess transportation barriers"_$Char(10)
        Set step = step + 1
        Set out = out_step_". Enroll in patient transport program or telehealth if available"_$Char(10)
        Set step = step + 1
    }
    If scoresLC["neighborhood"] {
        Set out = out_step_". Report housing issues to housing authority — document mold/safety concerns"_$Char(10)
        Set step = step + 1
    }
    If (scoresLC["social")||(scoresLC["isolat") {
        Set out = out_step_". Refer to community social connection program — senior center, peer support group"_$Char(10)
        Set step = step + 1
    }
    Set out = out_step_". Schedule 30-day follow-up call to assess progress on care plan goals"_$Char(10)
    Set out = out_$Char(10)_"Priority: Urgent if 4+ domains HIGH — escalate to supervising CHW"
    Quit out
}

ClassMethod TriggerFollowUp(patientId As %String, priority As %String = "routine", sdohFlags As %String = "") As %String
{
    If patientId = "" Quit "ERROR: patientId is required"
    Set sc = ##class(Ens.Director).GetProductionStatus(.prod, .state)
    If state '= 1 Quit "Production is not running. Call StartProduction first, then retry."
    Set request = ##class(CareConnect.Message.FollowUpRequest).%New()
    Set request.PatientId = patientId
    Set request.Priority = priority
    Set request.SDoHFlags = sdohFlags
    Set sc = ##class(Ens.Director).CreateBusinessService("CareConnect.Service.SDoHFollowUpBS", .bs)
    If $$$ISERR(sc) Quit "ERROR creating service: "_$System.Status.GetErrorText(sc)
    Set sc = bs.ProcessInput(request, .response)
    If $$$ISERR(sc) Quit "ERROR processing: "_$System.Status.GetErrorText(sc)
    Set jobId = ""
    If $IsObject(response) Set jobId = response.JobId
    Quit "Follow-up triggered for "_patientId_" (priority="_priority_") jobId="_jobId
}

ClassMethod GetInteropTraces(maxRows As %String = "20", sourceFilter As %String = "", targetFilter As %String = "") As %String
{
    Set rows = +maxRows
    If rows <= 0 Set rows = 20
    Set sql = "SELECT TOP "_rows_" ID,SourceConfigName,TargetConfigName,MessageBodyClassName,TimeCreated,Status FROM Ens.MessageHeader WHERE SourceConfigName != '' ORDER BY ID DESC"
    Set stmt = ##class(%SQL.Statement).%New()
    Set sc = stmt.%Prepare(sql)
    If $$$ISERR(sc) Quit "ERROR: "_$System.Status.GetErrorText(sc)
    Set rs = stmt.%Execute()
    Set out = ""
    Set count = 0
    While rs.%Next() {
        Set st = $Case(rs.Status,1:"Queued",2:"Delivered",3:"Acknowledged",4:"Error",5:"Discarded",6:"Aborted",7:"Suspended",8:"Cancelled",9:"Completed",:"Status:"_rs.Status)
        Set src = $Piece(rs.SourceConfigName,".",*)
        Set tgt = $Piece(rs.TargetConfigName,".",*)
        Set cls = $Piece(rs.MessageBodyClassName,".",*)
        Set out = out_"["_rs.ID_"] "_rs.TimeCreated_" | "_src_" -> "_tgt_" | "_cls_" | "_st_$Char(10)
        Set count = count + 1
    }
    If count = 0 Quit "No messages found. Start the production with StartProduction, then call TriggerFollowUp."
    Quit "Interoperability Traces ("_count_"):"_$Char(10)_out
}

ClassMethod GetProductionStatus() As %String
{
    Set sc = ##class(Ens.Director).GetProductionStatus(.prodName, .state)
    If $$$ISERR(sc) Quit "ERROR: "_$System.Status.GetErrorText(sc)
    If prodName = "" Quit "No production configured in namespace IRISAPP."
    Set stateText = $Case(state,1:"Running",2:"Stopped",3:"Suspended",4:"Troubled",:"Unknown("_state_")")
    Set out = "Production: "_prodName_$Char(10)_"Status: "_stateText_$Char(10)
    If state '= 1 Quit out
    Set stmt = ##class(%SQL.Statement).%New()
    Set sc2 = stmt.%Prepare("SELECT Name,Status,ActivityType FROM Ens.Config.Item WHERE Production=? ORDER BY ActivityType,Name")
    If $$$ISERR(sc2) Quit out
    Set rs = stmt.%Execute(prodName)
    Set out = out_"Components:"_$Char(10)
    While rs.%Next() {
        Set t = $Case(rs.ActivityType,1:"Service",2:"Process",3:"Operation",:"Host")
        Set s = $Case(rs.Status,1:"Running",2:"Stopped",3:"Suspended",:"Unknown")
        Set out = out_"  ["_t_"] "_rs.Name_": "_s_$Char(10)
    }
    Quit out
}

ClassMethod StartProduction() As %String
{
    Set sc = ##class(Ens.Director).GetProductionStatus(.prod, .state)
    If $$$ISERR(sc) Quit "ERROR checking status: "_$System.Status.GetErrorText(sc)
    If state = 1 Quit "Production already running: "_prod
    Set sc = ##class(Ens.Director).StartProduction("CareConnect.Production")
    If $$$ISERR(sc) Quit "ERROR starting production: "_$System.Status.GetErrorText(sc)
    Set sc = ##class(Ens.Director).GetProductionStatus(.prod, .state)
    Set stateText = $Case(state,1:"Running",2:"Stopped",3:"Suspended",:"Unknown("_state_")")
    Quit "Production started: "_prod_" ("_stateText_")"
}

}
