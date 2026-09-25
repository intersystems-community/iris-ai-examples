Include %occStatus

/// BO that fakes a patient record system.
Class Demo.AIHub.LookupBO Extends Sample.Interop.OTelBusinessOperation
{

Parameter INVOCATION = "Queue";

Method OnMessage(pRequest As %Library.Persistent, Output pResponse As %Library.Persistent) As %Status
{
    Set tSC = $$$OK
    If $IsObject(pRequest) && (pRequest.Traceparent '= "") {
        Set ^IRIS.Temp.MsgTraceparent($Job) = pRequest.Traceparent
    }
    Set tSC = ##super(pRequest, .pResponse)
    Quit tSC
}

Method OnProcessMessage(pRequest As %Library.Persistent, Output pResponse As %Library.Persistent) As %Status
{
    Set tSC = $$$OK
    Set pResponse = ##class(Demo.AIHub.PatientResponse).%New()
    Set tPatients("42") = "Jane Doe, 54, type 2 diabetes, last A1c 7.9% (2026-08-30), on metformin 1000mg BID."
    Set tPatients("7")  = "Omar Haddad, 67, CHF NYHA II, EF 38%, weight up 2.1 kg this week, on furosemide 40mg daily."
    Set tPatients("13") = "Mei Lin, 31, asthma, two ED visits in 90 days, albuterol refills monthly, no controller on file."
    Set tSummary = $Get(tPatients(pRequest.PatientId), "no record for this patient ID")
    Set pResponse.Summary = "Patient "_pRequest.PatientId_": "_tSummary
    Quit tSC
}

}
