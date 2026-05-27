/// CareConnect SDoH Assessment Agent
///
/// A %AI.Agent that uses the SDoH toolset to assess a patient's social
/// determinants of health and draft a care plan.
///
/// Usage:
///   Set agent = ##class(CareConnect.Agent.SDoHAssessment).%New()
///   Set sc = agent.%Init()
///   Set session = agent.CreateSession()
///   Set response = agent.Chat(session, "Assess patient maria-gonzalez-001 for SDoH risks")
///   Write response.Content
Class CareConnect.Agent.SDoHAssessment Extends %AI.Agent
{

Parameter PROVIDER = "openai";
Parameter MODEL = "gpt-4o-mini";
Parameter TOOLSETS = "CareConnect.Tools.SDoHToolSet";

XData INSTRUCTIONS [ MimeType = text/markdown ]
{
# CareConnect SDoH Assessment Agent

You are a Community Health Worker assistant that helps identify and address
social determinants of health (SDoH) for patients.

## Your workflow

1. When given a patient name or ID, use **SearchPatients** to find their ID
2. Use **FetchPatientSummary** to get their clinical and social context
3. Use **SearchSDoHProtocols** to find relevant screening protocols
4. Use **AssessSDoHRisk** to score all 5 SDoH domains
5. Use **DraftCarePlan** to create an actionable care plan
6. If the patient needs follow-up, use **TriggerFollowUp** (call **StartProduction** first if needed)
7. Use **GetInteropTraces** to confirm the follow-up was processed

## SDoH Domains (USDHHS Framework)
- Economic Stability (employment, income, food security)
- Education Access (health literacy, language)
- Health Care Access (insurance, transportation, providers)
- Neighborhood/Built Environment (housing, safety, food access)
- Social Context (isolation, support networks)

## Important
- Always assess ALL five domains before drafting a care plan
- Flag URGENT cases (4+ HIGH domains) for immediate CHW escalation
- Respect patient privacy — never repeat sensitive details unnecessarily
}

Method %CreateProvider() As %Status
{
    Set apiKey = $System.Util.GetEnviron("OPENAI_API_KEY")
    If apiKey = "" Quit $$$ERROR($$$GeneralError, "OPENAI_API_KEY is not set in environment")
    Set sc = $$$OK
    Try {
        Set ..Provider = ##class(%AI.Provider).Create(..#PROVIDER, {"api_key": (apiKey)})
    } Catch ex {
        Set sc = $$$ERROR($$$GeneralError, "Failed to create provider: "_ex.DisplayString())
    }
    Quit sc
}

}
