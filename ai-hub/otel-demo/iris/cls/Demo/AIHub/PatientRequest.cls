/// Request carried from the tool into the production. Traceparent is persisted so
/// the W3C context survives the hop into BP and BO jobs.
Class Demo.AIHub.PatientRequest Extends Ens.Request
{

Property PatientId As %String(MAXLEN = 64);

Property Traceparent As %String(MAXLEN = 64);

}
