/// Minimal response message for CareConnectTrace E2E test.
Class Sample.Interop.Examples.CareConnectResponse Extends Ens.Response
{

Property Traceparent As %String;

Storage Default
{
<Data name="CareConnectResponseDefaultData">
<Subscript>"CareConnectResponse"</Subscript>
<Value name="1">
<Value>Traceparent</Value>
</Value>
</Data>
<DefaultData>CareConnectResponseDefaultData</DefaultData>
<Type>%Storage.Persistent</Type>
}

}
