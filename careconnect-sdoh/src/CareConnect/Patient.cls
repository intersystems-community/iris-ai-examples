/// Demo patient table — replaces FHIR dependency for hackathon use.
/// Seeded by CareConnect.Setup.DemoData.Load()
Class CareConnect.Patient Extends %Persistent
{

Property PatientId   As %String(MAXLEN = 100) [ Required ];
Property Name        As %String(MAXLEN = 200) [ Required ];
Property Demographics As %String(MAXLEN = 50);
Property Conditions  As %String(MAXLEN = 2000);
Property Observations As %String(MAXLEN = 2000);
Property SDoHFlags   As %String(MAXLEN = 500);
Property Notes       As %String(MAXLEN = 4000);

Index PatientIdIdx On PatientId [ Unique ];

Storage Default
{
<Data name="PatientDefaultData">
<Value name="1"><Value>%%CLASSNAME</Value></Value>
<Value name="2"><Value>PatientId</Value></Value>
<Value name="3"><Value>Name</Value></Value>
<Value name="4"><Value>Demographics</Value></Value>
<Value name="5"><Value>Conditions</Value></Value>
<Value name="6"><Value>Observations</Value></Value>
<Value name="7"><Value>SDoHFlags</Value></Value>
<Value name="8"><Value>Notes</Value></Value>
</Data>
<DataLocation>^CareConnect.PatientD</DataLocation>
<DefaultData>PatientDefaultData</DefaultData>
<IdLocation>^CareConnect.PatientD</IdLocation>
<IndexLocation>^CareConnect.PatientI</IndexLocation>
<Type>%Storage.Persistent</Type>
}

}
