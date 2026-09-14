/// Minimal production for CareConnectTrace E2E test.
/// Wires EnsLib.Testing.Service → CareConnectBP → CareConnectBO.
///
/// EnsLib.Testing.Process is required, not optional: a synchronous
/// <method>EnsLib.Testing.Service.SendTestRequest</method> dispatches through it,
/// and without the item every send fails with
/// &lt;Ens&gt;ErrBusinessDispatchNameNotRegistered while the production itself still
/// reports as started.
Class Sample.Interop.Examples.CareConnectProduction Extends Ens.Production
{

XData ProductionDefinition
{
<Production Name="Sample.Interop.Examples.CareConnectProduction" LogGeneralTraceEvents="false">
  <Description>OTel interop E2E test production</Description>
  <ActorPoolSize>1</ActorPoolSize>
  <Item Name="EnsLib.Testing.Service" Category="" ClassName="EnsLib.Testing.Service" PoolSize="1" Enabled="true" Foreground="false" Comment="" LogTraceEvents="false" Schedule="">
  </Item>
  <Item Name="EnsLib.Testing.Process" Category="" ClassName="EnsLib.Testing.Process" PoolSize="1" Enabled="true" Foreground="false" Comment="" LogTraceEvents="false" Schedule="">
  </Item>
  <Item Name="CareConnectBP" Category="" ClassName="Sample.Interop.Examples.CareConnectBP" PoolSize="1" Enabled="true" Foreground="false" Comment="" LogTraceEvents="false" Schedule="">
  </Item>
  <Item Name="CareConnectBO" Category="" ClassName="Sample.Interop.Examples.CareConnectBO" PoolSize="1" Enabled="true" Foreground="false" Comment="" LogTraceEvents="false" Schedule="">
  </Item>
</Production>
}

}
