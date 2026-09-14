Include %AI

/// CareConnect SDoH ToolSet
///
/// Exposes social determinants of health (SDoH) tools via the AI Hub MCP server.
/// Demo patient data lives in the CareConnect.Patient SQL table - no FHIR dependency.
///
/// Tools exposed:
///   SearchPatients          - list/search the demo patient roster
///   FetchPatientSummary     - get clinical summary for a patient
///   SearchSDoHProtocols     - find screening protocols matching conditions
///   AssessSDoHRisk          - score six SDoH domains (five USDHHS plus transportation access)
///   DraftCarePlan           - generate an actionable care plan
///   TriggerFollowUp         - fire the Interoperability follow-up workflow
///   GetInteropTraces        - view recent message flow from the production
///   GetProductionStatus     - check whether the production is running
///   StartProduction         - start CareConnect.Production
Class CareConnect.Tools.SDoHToolSet Extends %AI.ToolSet
{

XData Definition [ MimeType = application/xml ]
{
<ToolSet Name="SDoHTools">
  <Description>CareConnect SDoH Tools - patient lookup, risk assessment, care planning, interop tracing, knowledge graph</Description>

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
    <Description>Score a patient on six SDoH domains (five USDHHS plus transportation access) using clinical summary and matched protocols.</Description>
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

  <Tool Name="SearchClinicalNotes" Method="SearchClinicalNotes">
    <Description>Search FHIR DocumentReference clinical notes for a patient. Returns matching note summaries. Requires the FHIR server to be running.</Description>
  </Tool>

  <Tool Name="GetPatientGraphNeighborhood" Method="GetPatientGraphNeighborhood">
    <Description>Given a patient ID, extract their conditions and traverse the knowledge graph to find related clinical concepts, comorbidities, and biomedical relationships. Requires the IVG knowledge graph to be running (research preview).</Description>
  </Tool>

  <Tool Name="FindRelatedEvidence" Method="FindRelatedEvidence">
    <Description>Search the biomedical knowledge graph for evidence related to a clinical concept or condition. Returns ranked related concepts from the graph. Requires the IVG knowledge graph to be running (research preview).</Description>
  </Tool>

  <Tool Name="GetClinicalPathway" Method="GetClinicalPathway">
    <Description>Full clinical reasoning pipeline: takes a patient ID and a clinical question, retrieves their FHIR conditions, bridges ICD codes to the knowledge graph via UMLS, runs Personalized PageRank to find related concepts, and returns a ranked evidence pathway with provenance. Requires IVG stack (research preview).</Description>
  </Tool>

  <Tool Name="CheckProtocolContradictions" Method="CheckProtocolContradictions">
    <Description>Before citing any SDoH protocol, call this with the concept name (e.g. "food insecurity screening"). If UNRESOLVED contradictions exist between guidelines, returns BLOCKED status with both conflicting statements. The agent MUST NOT choose between them — escalate to clinical lead instead. Requires IVG stack.</Description>
  </Tool>

  <Tool Name="RecordProtocolDecision" Method="RecordProtocolDecision">
    <Description>Human-approved write path. Records a resolved SDoH protocol decision into the persistent knowledge graph. Requires: concept, domain, rule, source, rationale. Optional: effective_date (ISO format). The agent may PROPOSE a decision but a human must confirm before calling this tool. Requires IVG stack.</Description>
  </Tool>

  <Tool Name="GetKnowledgeContext" Method="GetKnowledgeContext">
    <Description>Retrieve all governing protocol decisions for an SDoH concept from the persistent knowledge graph. Use this to ground answers with traceable, source-linked evidence before drafting a care plan. Requires IVG stack.</Description>
  </Tool>

  <Tool Name="GroundAnswerWithCitations" Method="GroundAnswerWithCitations">
    <Description>Optional Parseltongue grounding layer. Verifies each claim in a draft answer against verbatim quotes from source documents and adds inline [SOURCE: ...] citations. Only active when PARSELTONGUE_GROUNDING=true on the IVG service. Call after GetKnowledgeContext and after contradiction gate clears. Safe to call always — returns original answer unchanged when grounding is disabled.</Description>
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
    Set health = $Select((summaryLC["uninsur")||(summaryLC["no doctor")||(summaryLC["clinic"):"HIGH", 1:"MEDIUM")
    Set nbhd = $Select((summaryLC["housing")||(summaryLC["mold")||(summaryLC["unsafe")||(summaryLC["food bank"):"HIGH", 1:"LOW")
    Set social = $Select((summaryLC["alone")||(summaryLC["isolat")||(summaryLC["no family")||(summaryLC["no support"):"HIGH", 1:"LOW")
    Set transport = $Select((summaryLC["no car")||(summaryLC["no ride")||(summaryLC["no bus")||(summaryLC["transport")||(summaryLC["transit")||(summaryLC["missed appointment")||(summaryLC["can't get to")||(summaryLC["cannot get to"):"HIGH", 1:"LOW")
    Set out = "SDoH Risk Assessment for "_patientId_":"_$Char(10)
    Set out = out_"  Economic Stability:      "_econ_$Char(10)
    Set out = out_"  Education Access:        "_edu_$Char(10)
    Set out = out_"  Health Care Access:      "_health_$Char(10)
    Set out = out_"  Neighborhood/Built Env:  "_nbhd_$Char(10)
    Set out = out_"  Social Context:          "_social_$Char(10)
    Set out = out_"  Transportation Access:   "_transport_$Char(10)
    Set highCount = 0
    For d = econ, edu, health, nbhd, social, transport { If d = "HIGH" Set highCount = highCount + 1 }
    Set priority = $Select(highCount >= 5:"URGENT", highCount >= 3:"HIGH", 1:"ROUTINE")
    Set out = out_"Overall Priority: "_priority_" ("_highCount_"/6 domains elevated)"
    Quit out
}

ClassMethod DraftCarePlan(patientId As %String, sdohScores As %String) As %String
{
    If patientId = "" Quit "ERROR: patientId is required"
    Set scoresLC = $ZCONVERT(sdohScores, "L")
    Set out = "Care Plan for "_patientId_":"_$Char(10,10)
    Set step = 1
    If scoresLC["economic" {
        Set out = out_step_". Connect with financial assistance programs - SNAP, Medicaid, emergency rental assistance"_$Char(10)
        Set step = step + 1
    }
    If (scoresLC["health care")||(scoresLC["transport") {
        Set out = out_step_". Schedule CHW home visit within 5 days - assess transportation barriers"_$Char(10)
        Set step = step + 1
        Set out = out_step_". Enroll in patient transport program or telehealth if available"_$Char(10)
        Set step = step + 1
    }
    If scoresLC["neighborhood" {
        Set out = out_step_". Report housing issues to housing authority - document mold/safety concerns"_$Char(10)
        Set step = step + 1
    }
    If (scoresLC["social")||(scoresLC["isolat") {
        Set out = out_step_". Refer to community social connection program - senior center, peer support group"_$Char(10)
        Set step = step + 1
    }
    Set out = out_step_". Schedule 30-day follow-up call to assess progress on care plan goals"_$Char(10)
    Set out = out_$Char(10)_"Priority: Urgent if 5+ domains HIGH - escalate to supervising CHW"
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

ClassMethod SearchClinicalNotes(patientId As %String, query As %String = "") As %String
{
    If patientId = "" Quit "ERROR: patientId is required"
    Set fhirHost = $SYSTEM.Util.GetEnviron("FHIR_HOST")
    If fhirHost = "" Set fhirHost = "careconnect-iris-fhir"
    Set httpReq = ##class(%Net.HttpRequest).%New()
    Set httpReq.Server = fhirHost
    Set httpReq.Port = 52773
    Set httpReq.Username = "_SYSTEM"
    Set httpReq.Password = "SYS"
    Do httpReq.SetHeader("Accept", "application/fhir+json")
    Set path = "/csp/healthshare/demo/fhir/r4/DocumentReference?patient="_patientId_"&_count=10"
    If query '= "" Set path = path_"&description:contains="_$ZCVT(query,"O","URL")
    Set sc = httpReq.Get(path)
    If $$$ISERR(sc) Quit "FHIR server unavailable: "_$System.Status.GetErrorText(sc)
    If httpReq.HttpResponse.StatusCode '= 200 Quit "FHIR returned HTTP "_httpReq.HttpResponse.StatusCode_" - server may not be running"
    Set body = httpReq.HttpResponse.Data.Read(32768)
    If body = "" Quit "No clinical notes found for patient "_patientId
    Set bundle = ##class(%DynamicObject).%FromJSON(body)
    Set entries = bundle.entry
    If '$IsObject(entries) Quit "No clinical notes found for patient "_patientId
    Set out = "Clinical notes for "_patientId_":"_$Char(10)
    Set iter = entries.%GetIterator()
    While iter.%GetNext(.k, .entry) {
        Set res = entry.resource
        If $IsObject(res) {
            Set desc = res.description
            If desc = "" Set desc = "(no description)"
            Set status = res.status
            Set date = res.date
            Set out = out_"  ["_status_"] "_date_" - "_desc_$Char(10)
        }
    }
    Quit out
}

ClassMethod GetPatientGraphNeighborhood(patientId As %String, hops As %String = "1") As %String
{
    If patientId = "" Quit "ERROR: patientId is required"
    Set ivgHost = $SYSTEM.Util.GetEnviron("IVG_HOST")
    If ivgHost = "" Set ivgHost = "careconnect-ivg-bolt"
    Set fhirHost = $SYSTEM.Util.GetEnviron("FHIR_HOST")
    If fhirHost = "" Set fhirHost = "careconnect-iris-fhir"
    Set fhirUrl = "http://"_fhirHost_":52773/csp/healthshare/demo/fhir/r4"
    Set cypher = "MATCH (n)-[r*1.."_hops_"]-(m) WHERE n.id IN $patient_anchors RETURN DISTINCT n.id AS source, type(r[0]) AS rel, m.id AS target, m.name AS target_name LIMIT 20"
    Set ivgApiKey = $SYSTEM.Util.GetEnviron("IVG_API_KEY")
    If ivgApiKey = "" Set ivgApiKey = "changeme"
    Set httpReq = ##class(%Net.HttpRequest).%New()
    Set httpReq.Server = ivgHost
    Set httpReq.Port = 8000
    Set httpReq.ContentType = "application/json"
    Do httpReq.SetHeader("x-api-key", $SYSTEM.Util.GetEnviron("IVG_API_KEY"))
    Set body = ##class(%DynamicObject).%New()
    Do body.%Set("query", cypher)
    Do body.%Set("fhir_patient_id", patientId)
    Do body.%Set("fhir_base_url", fhirUrl)
    Set sc = httpReq.EntityBody.Write(body.%ToJSON())
    Set sc = httpReq.Post("/api/cypher")
    If $$$ISERR(sc) Quit "Knowledge graph unavailable (research preview - start with: docker compose --profile ivg up -d)"
    If httpReq.HttpResponse.StatusCode = 400 {
        Set errBody = httpReq.HttpResponse.Data.Read(500)
        If (errBody["patient_anchors")||(errBody["empty") Quit "No ICD-10 to KG mappings found for "_patientId_". Load UMLS bridges first — or the FHIR server has no Condition resources for this patient."
        Quit "IVG query error: "_errBody
    }
    If httpReq.HttpResponse.StatusCode '= 200 Quit "IVG returned HTTP "_httpReq.HttpResponse.StatusCode
    Set resp = ##class(%DynamicObject).%FromJSON(httpReq.HttpResponse.Data.Read(32768))
    Set results = resp.%Get("results")
    If '$IsObject(results) Quit "No graph results for patient "_patientId_". The knowledge graph may be empty - load clinical bridges first."
    Set out = "Knowledge graph neighborhood for "_patientId_":"_$Char(10)
    Set iter = results.%GetIterator()
    Set count = 0
    While iter.%GetNext(.k, .row) {
        Set tname = row.target_name
        If tname = "" Set tname = row.target
        Set out = out_"  "_row.source_" -["_row.rel_"]-> "_tname_$Char(10)
        Set count = count + 1
    }
    If count = 0 Quit "No graph connections found for patient "_patientId_". Load UMLS bridges or seed demo data first."
    Quit out
}

ClassMethod FindRelatedEvidence(concept As %String) As %String
{
    If concept = "" Quit "ERROR: concept is required"
    Set ivgHost = $SYSTEM.Util.GetEnviron("IVG_HOST")
    If ivgHost = "" Set ivgHost = "careconnect-ivg-bolt"
    Set conceptLC = $ZCONVERT(concept, "L")
    Set conceptLC = $Replace(conceptLC, " ", "_")
    Set cypher = "MATCH (n) WHERE toLower(n.id) CONTAINS '"_conceptLC_"' OR toLower(n.name) CONTAINS '"_$ZCONVERT(concept,"L")_"' WITH n MATCH (n)-[r]-(m) RETURN n.id AS concept, type(r) AS relationship, m.id AS related, m.name AS related_name LIMIT 25"
    Set ivgApiKey = $SYSTEM.Util.GetEnviron("IVG_API_KEY")
    If ivgApiKey = "" Set ivgApiKey = "changeme"
    Set httpReq = ##class(%Net.HttpRequest).%New()
    Set httpReq.Server = ivgHost
    Set httpReq.Port = 8000
    Set httpReq.ContentType = "application/json"
    Do httpReq.SetHeader("X-API-Key", ivgApiKey)
    Set body = ##class(%DynamicObject).%New()
    Do body.%Set("query", cypher)
    Set sc = httpReq.EntityBody.Write(body.%ToJSON())
    Set sc = httpReq.Post("/api/cypher")
    If $$$ISERR(sc) Quit "Knowledge graph unavailable (research preview - start IVG stack with: docker compose --profile ivg up -d)"
    If httpReq.HttpResponse.StatusCode '= 200 Quit "IVG returned HTTP "_httpReq.HttpResponse.StatusCode
    Set resp = ##class(%DynamicObject).%FromJSON(httpReq.HttpResponse.Data.Read(32768))
    Set results = resp.%Get("results")
    If '$IsObject(results) Quit "No evidence found for: "_concept
    Set out = "Related evidence for '"_concept_"' from knowledge graph:"_$Char(10)
    Set iter = results.%GetIterator()
    Set count = 0
    While iter.%GetNext(.k, .row) {
        Set rname = row.related_name
        If rname = "" Set rname = row.related
        Set out = out_"  "_row.concept_" -["_row.relationship_"]-> "_rname_$Char(10)
        Set count = count + 1
    }
    If count = 0 Quit "No evidence found for '"_concept_"'. The knowledge graph may be empty."
    Quit out
}

ClassMethod GetClinicalPathway(patientId As %String, clinicalQuestion As %String = "") As %String
{
    If patientId = "" Quit "ERROR: patientId is required"
    Set ivgHost = $SYSTEM.Util.GetEnviron("IVG_HOST")
    If ivgHost = "" Set ivgHost = "careconnect-ivg-bolt"
    Set fhirHost = $SYSTEM.Util.GetEnviron("FHIR_HOST")
    If fhirHost = "" Set fhirHost = "careconnect-iris-fhir"
    Set fhirUrl = "http://"_fhirHost_":52773/csp/healthshare/demo/fhir/r4"
    Set httpReq = ##class(%Net.HttpRequest).%New()
    Set httpReq.Server = ivgHost
    Set httpReq.Port = 8000
    Set httpReq.ContentType = "application/json"
    Set ivgApiKey = $SYSTEM.Util.GetEnviron("IVG_API_KEY")
    If ivgApiKey = "" Set ivgApiKey = "changeme"
    Do httpReq.SetHeader("X-API-Key", ivgApiKey)
    Set body = ##class(%DynamicObject).%New()
    Do body.%Set("patient_id", patientId)
    Do body.%Set("query", clinicalQuestion)
    Do body.%Set("fhir_base_url", fhirUrl)
    Do body.%Set("top_k", 10, "number")
    Do body.%Set("ppr_top_k", 20, "number")
    Set sc = httpReq.EntityBody.Write(body.%ToJSON())
    Set sc = httpReq.Post("/api/pipeline")
    If $$$ISERR(sc) Quit "IVG pipeline unavailable (research preview - start with: docker compose --profile ivg up -d)"
    If httpReq.HttpResponse.StatusCode = 400 {
        Set errBody = httpReq.HttpResponse.Data.Read(1024)
        Quit "Pipeline error: "_errBody
    }
    If httpReq.HttpResponse.StatusCode '= 200 Quit "IVG returned HTTP "_httpReq.HttpResponse.StatusCode
    Set resp = ##class(%DynamicObject).%FromJSON(httpReq.HttpResponse.Data.Read(65536))
    Set anchors = resp.%Get("anchors")
    Set pprResults = resp.%Get("ppr_results")
    Set provenance = resp.%Get("provenance")
    Set out = "Clinical Pathway for "_patientId
    If clinicalQuestion '= "" Set out = out_" re: "_clinicalQuestion
    Set out = out_$Char(10,10)
    If $IsObject(anchors) {
        Set out = out_"KG Anchors (FHIR conditions bridged to knowledge graph):"_$Char(10)
        Set iter = anchors.%GetIterator()
        While iter.%GetNext(.k, .v) { Set out = out_"  "_v_$Char(10) }
        Set out = out_$Char(10)
    }
    If '$IsObject(pprResults) || (pprResults.%Size() = 0) {
        If '$IsObject(anchors) || (anchors.%Size() = 0) {
            Quit out_"No FHIR conditions found or no bridge mappings loaded."_$Char(10)_"Load UMLS bridges via: scripts/ingest/load_umls_bridges.py"
        }
        Quit out_"Anchors found but no PPR results. The knowledge graph may need more data."
    }
    Set out = out_"Related concepts (Personalized PageRank from condition anchors):"_$Char(10)
    Set iter = pprResults.%GetIterator()
    Set rank = 1
    While iter.%GetNext(.k, .node) {
        Set nid = node.node_id
        If nid = "" Set nid = node.id
        Set score = node.score
        If score = "" Set score = node.ppr_score
        Set out = out_"  "_rank_". "_nid
        If score '= "" Set out = out_" (score: "_score_")"
        Set out = out_$Char(10)
        Set rank = rank + 1
        If rank > 10 Quit
    }
    Quit out
}

/// Check for unresolved guideline contradictions for an SDoH concept.
/// Returns BLOCKED if any exist — agent must NOT choose between conflicting guidelines.
ClassMethod CheckProtocolContradictions(concept As %String, domain As %String = "") As %String
{
    If concept = "" Quit "ERROR: concept is required"
    Set ivgHost = $SYSTEM.Util.GetEnviron("IVG_HOST")
    If ivgHost = "" Set ivgHost = "careconnect-ivg-bolt"
    Set ivgApiKey = $SYSTEM.Util.GetEnviron("IVG_API_KEY")
    If ivgApiKey = "" Set ivgApiKey = "changeme"
    Set httpReq = ##class(%Net.HttpRequest).%New()
    Set httpReq.Server = ivgHost
    Set httpReq.Port = 8000
    Set httpReq.ContentType = "application/json"
    Do httpReq.SetHeader("X-API-Key", ivgApiKey)
    Set body = ##class(%DynamicObject).%New()
    Do body.%Set("concept", concept)
    Do body.%Set("domain", domain)
    Set sc = httpReq.EntityBody.Write(body.%ToJSON())
    Set sc = httpReq.Post("/api/knowledge/check-contradictions")
    If $$$ISERR(sc) Quit "Knowledge layer unavailable (start with: docker compose --profile ivg up -d)"
    If httpReq.HttpResponse.StatusCode '= 200 Quit "Knowledge layer returned HTTP "_httpReq.HttpResponse.StatusCode
    Set resp = ##class(%DynamicObject).%FromJSON(httpReq.HttpResponse.Data.Read(32768))
    Set blocked = resp.%Get("blocked")
    Set count = resp.%Get("unresolved_count")
    If 'blocked Quit "NO_CONTRADICTIONS: Safe to cite protocols for '"_concept_"'."
    Set out = "BLOCKED: "_count_" unresolved guideline contradiction(s) found for '"_concept_"'."_$Char(10)
    Set out = out_"Do NOT choose between them. Escalate to clinical lead."_$Char(10,10)
    Set cts = resp.%Get("contradictions")
    If $IsObject(cts) {
        Set iter = cts.%GetIterator()
        While iter.%GetNext(.k, .ct) {
            Set out = out_"Contradiction: "_ct.id_$Char(10)
            Set out = out_"  A: "_ct.statement_a_" ["_ct.source_a_"]"_$Char(10)
            Set out = out_"  B: "_ct.statement_b_" ["_ct.source_b_"]"_$Char(10)
            Set out = out_"  Owner: "_ct.owner_$Char(10,10)
        }
    }
    Quit out
}

/// Record a human-approved SDoH protocol decision into the persistent knowledge graph.
/// The agent may PROPOSE values but a human must explicitly confirm before this is called.
ClassMethod RecordProtocolDecision(concept As %String, domain As %String, rule As %String, source As %String, rationale As %String, effectiveDate As %String = "") As %String
{
    If concept = "" || (domain = "") || (rule = "") || (source = "") Quit "ERROR: concept, domain, rule, and source are required"
    Set ivgHost = $SYSTEM.Util.GetEnviron("IVG_HOST")
    If ivgHost = "" Set ivgHost = "careconnect-ivg-bolt"
    Set ivgApiKey = $SYSTEM.Util.GetEnviron("IVG_API_KEY")
    If ivgApiKey = "" Set ivgApiKey = "changeme"
    Set httpReq = ##class(%Net.HttpRequest).%New()
    Set httpReq.Server = ivgHost
    Set httpReq.Port = 8000
    Set httpReq.ContentType = "application/json"
    Do httpReq.SetHeader("X-API-Key", ivgApiKey)
    Set body = ##class(%DynamicObject).%New()
    Do body.%Set("concept", concept)
    Do body.%Set("domain", domain)
    Do body.%Set("rule", rule)
    Do body.%Set("source", source)
    Do body.%Set("rationale", rationale)
    If effectiveDate '= "" Do body.%Set("effective_date", effectiveDate)
    Set sc = httpReq.EntityBody.Write(body.%ToJSON())
    Set sc = httpReq.Post("/api/knowledge/record-decision")
    If $$$ISERR(sc) Quit "Knowledge layer unavailable (start with: docker compose --profile ivg up -d)"
    If httpReq.HttpResponse.StatusCode '= 200 Quit "Knowledge layer returned HTTP "_httpReq.HttpResponse.StatusCode
    Set resp = ##class(%DynamicObject).%FromJSON(httpReq.HttpResponse.Data.Read(4096))
    Set decisionId = resp.%Get("decision_id")
    Set embedded = resp.%Get("embedded")
    Set embStr = $Select(embedded:"yes", 1:"no (sentence-transformers unavailable)")
    Quit "Decision recorded: "_decisionId_$Char(10)_"Concept: "_concept_" | Source: "_source_$Char(10)_"Vector-searchable: "_embStr
}

/// Retrieve governing protocol decisions for an SDoH concept from the persistent knowledge graph.
/// Use before drafting care plans to ground recommendations with traceable, source-linked evidence.
ClassMethod GetKnowledgeContext(concept As %String) As %String
{
    If concept = "" Quit "ERROR: concept is required"
    Set ivgHost = $SYSTEM.Util.GetEnviron("IVG_HOST")
    If ivgHost = "" Set ivgHost = "careconnect-ivg-bolt"
    Set ivgApiKey = $SYSTEM.Util.GetEnviron("IVG_API_KEY")
    If ivgApiKey = "" Set ivgApiKey = "changeme"
    Set httpReq = ##class(%Net.HttpRequest).%New()
    Set httpReq.Server = ivgHost
    Set httpReq.Port = 8000
    Set httpReq.ContentType = "application/json"
    Do httpReq.SetHeader("X-API-Key", ivgApiKey)
    Set body = ##class(%DynamicObject).%New()
    Do body.%Set("concept", concept)
    Set sc = httpReq.EntityBody.Write(body.%ToJSON())
    Set sc = httpReq.Post("/api/knowledge/context")
    If $$$ISERR(sc) Quit "Knowledge layer unavailable (start with: docker compose --profile ivg up -d)"
    If httpReq.HttpResponse.StatusCode '= 200 Quit "Knowledge layer returned HTTP "_httpReq.HttpResponse.StatusCode
    Set resp = ##class(%DynamicObject).%FromJSON(httpReq.HttpResponse.Data.Read(32768))
    If 'resp.%Get("found") Quit "No knowledge context found for '"_concept_"'. The knowledge graph may not be seeded yet."
    Set out = "Knowledge context for '"_resp.%Get("concept")_"' (domain: "_resp.%Get("domain")_"):"_$Char(10)
    Set aliases = resp.%Get("aliases")
    If $IsObject(aliases) && (aliases.%Size() > 0) {
        Set aout = ""
        Set iter = aliases.%GetIterator()
        While iter.%GetNext(.k, .v) { Set aout = aout_$Select(aout="":"", 1:", ")_v }
        Set out = out_"  Aliases: "_aout_$Char(10)
    }
    Set out = out_$Char(10)
    Set decisions = resp.%Get("decisions")
    If '$IsObject(decisions) || (decisions.%Size() = 0) {
        Quit out_"No governing decisions recorded yet for this concept."
    }
    Set out = out_"Governing decisions:"_$Char(10)
    Set iter = decisions.%GetIterator()
    While iter.%GetNext(.k, .d) {
        Set out = out_"  ["_d.effective_date_"] "_d.source_$Char(10)
        Set out = out_"    Rule: "_d.rule_$Char(10)
        Set out = out_"    Rationale: "_d.rationale_$Char(10,10)
    }
    Quit out
}

/// Optional Parseltongue grounding layer.
/// Verifies each claim in the draft answer against verbatim quotes from the source
/// documents and adds inline [SOURCE: ...] citations. Only runs when the IVG service
/// has PARSELTONGUE_GROUNDING=true. Safe to call always — returns original answer
/// when grounding is disabled so existing flows are unaffected.
///
/// Arguments:
///   answer    - Draft answer text to ground
///   decisions - JSON array string of decisions from GetKnowledgeContext
///   concept   - SDoH concept (for context label)
ClassMethod GroundAnswerWithCitations(answer As %String, decisions As %String = "[]", concept As %String = "") As %String
{
    If answer = "" Quit "ERROR: answer is required"
    Set ivgHost = $SYSTEM.Util.GetEnviron("IVG_HOST")
    If ivgHost = "" Set ivgHost = "careconnect-ivg-bolt"
    Set ivgApiKey = $SYSTEM.Util.GetEnviron("IVG_API_KEY")
    If ivgApiKey = "" Set ivgApiKey = "changeme"

    Set httpReq = ##class(%Net.HttpRequest).%New()
    Set httpReq.Server = ivgHost
    Set httpReq.Port = 8000
    Set httpReq.ContentType = "application/json"
    Do httpReq.SetHeader("X-API-Key", ivgApiKey)

    Set body = ##class(%DynamicObject).%New()
    Do body.%Set("answer", answer)
    Do body.%Set("concept", concept)
    // Parse decisions JSON string into array for the request body
    Set decArr = ##class(%DynamicArray).%FromJSON(decisions)
    Do body.%Set("decisions", decArr)

    Set sc = httpReq.EntityBody.Write(body.%ToJSON())
    Set sc = httpReq.Post("/api/knowledge/ground-answer")
    If $$$ISERR(sc) Quit answer_" [Grounding unavailable — start IVG stack]"
    If httpReq.HttpResponse.StatusCode '= 200 Quit answer_" [Grounding error: HTTP "_httpReq.HttpResponse.StatusCode_"]"

    Set resp = ##class(%DynamicObject).%FromJSON(httpReq.HttpResponse.Data.Read(65536))
    If 'resp.%Get("enabled") Quit answer  // Grounding disabled — return as-is

    Set out = "=== Parseltongue Grounding Report ==="_$Char(10)
    Set verified = resp.%Get("verified_claims")
    Set unverified = resp.%Get("unverified_claims")
    Set issues = resp.%Get("consistency_issues")

    Set vCount = $Select($IsObject(verified):verified.%Size(), 1:0)
    Set out = out_"Verified claims: "_vCount_$Char(10)
    If $IsObject(verified) {
        Set iter = verified.%GetIterator()
        While iter.%GetNext(.k, .v) {
            Set out = out_"  [OK] ["_v.source_"] "_$Extract(v.quote,1,80)_$Char(10)
        }
    }

    Set uCount = $Select($IsObject(unverified):unverified.%Size(), 1:0)
    If uCount > 0 {
        Set out = out_"Unverified claims: "_uCount_$Char(10)
        Set iter = unverified.%GetIterator()
        While iter.%GetNext(.k, .v) { Set out = out_"  [UNVERIFIED] "_v_$Char(10) }
    }

    Set iCount = $Select($IsObject(issues):issues.%Size(), 1:0)
    If iCount > 0 {
        Set out = out_"Consistency issues: "_iCount_$Char(10)
        Set iter = issues.%GetIterator()
        While iter.%GetNext(.k, .v) { Set out = out_"  [!] "_v_$Char(10) }
    }

    Set out = out_$Char(10)_"Grounded answer:"_$Char(10)_resp.%Get("grounded_answer")
    Quit out
}

}
