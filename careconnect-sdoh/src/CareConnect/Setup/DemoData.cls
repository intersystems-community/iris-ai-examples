/// Seeds the demo patient table with three representative SDoH cases.
/// Safe to call multiple times — skips if data already present.
Class CareConnect.Setup.DemoData Extends %RegisteredObject
{

ClassMethod Load() As %Status
{
    Set stmt = ##class(%SQL.Statement).%New()
    Set sc = stmt.%Prepare("SELECT COUNT(*) ct FROM CareConnect.Patient")
    Set rs = stmt.%Execute()
    If rs.%Next() && (rs.ct > 0) {
        Write "Demo data already loaded (", rs.ct, " patients).", !
        Quit $$$OK
    }

    Set ins = ##class(%SQL.Statement).%New()
    Set sc = ins.%Prepare("INSERT INTO CareConnect.Patient (PatientId,Name,Demographics,Conditions,Observations,SDoHFlags,Notes) VALUES (?,?,?,?,?,?,?)")

    Do ins.%Execute(
        "maria-gonzalez-001",
        "Maria Gonzalez",
        "42F",
        "Type 2 Diabetes Mellitus|Hypertension",
        "HbA1c = 8.9|Blood Pressure = 148/92",
        "food_insecurity|no_transport|unemployed",
        "Patient reports difficulty affording insulin. Lives alone, no transport. Recently lost job, relying on food bank. Primary language Spanish, limited English.")

    Do ins.%Execute(
        "james-okafor-002",
        "James Okafor",
        "67M",
        "Congestive Heart Failure|Depression",
        "BNP = 540|PHQ-9 = 14",
        "social_isolation|housing_issues|medication_cost",
        "Socially isolated since wife passed. Lives in subsidized housing with mold issues. Skipping medications due to cost. No family nearby.")

    Do ins.%Execute(
        "sarah-kim-003",
        "Sarah Kim",
        "29F",
        "Prenatal care 28wk|Iron deficiency anemia",
        "Hemoglobin = 9.8",
        "uninsured|food_insecurity|unstable_housing",
        "Uninsured, recently immigrated. Food insecure - skipping meals. No stable housing, staying with relatives. Transport barrier to clinic.")

    Write "Demo patients loaded: 3 records.", !
    Quit $$$OK
}

}
