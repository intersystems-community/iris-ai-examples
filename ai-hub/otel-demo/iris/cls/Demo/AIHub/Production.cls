/// AI Hub e2e telemetry demo production: tool -> BS -> BP -> BO.
Class Demo.AIHub.Production Extends Ens.Production
{

XData ProductionDefinition
{
<Production Name="Demo.AIHub.Production" LogGeneralTraceEvents="false">
  <Description>AI Hub e2e OTel demo</Description>
  <ActorPoolSize>1</ActorPoolSize>
  <Item Name="ToolService" ClassName="Demo.AIHub.ToolService" PoolSize="0" Enabled="true"/>
  <Item Name="LookupBP" ClassName="Demo.AIHub.LookupBP" PoolSize="1" Enabled="true"/>
  <Item Name="LookupBO" ClassName="Demo.AIHub.LookupBO" PoolSize="1" Enabled="true"/>
</Production>
}

}
