/// Minimal request message for CareConnectTrace E2E test.
Class Sample.Interop.Examples.CareConnectRequest Extends Ens.Request
{

Property Payload As %String;

Storage Default
{
<Data name="CareConnectRequestDefaultData">
<Subscript>"CareConnectRequest"</Subscript>
<Value name="1">
<Value>Payload</Value>
</Value>
</Data>
<DefaultData>CareConnectRequestDefaultData</DefaultData>
<Type>%Storage.Persistent</Type>
}

}
