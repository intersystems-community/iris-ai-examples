/// CareConnect SDoH Follow-Up Production
Class CareConnect.Production Extends Ens.Production
{

XData ProductionDefinition
{
<Production Name="CareConnect.Production" LogGeneralTraceEvents="true">
  <ActorPoolSize>2</ActorPoolSize>
  <Item Name="CareConnect.Service.SDoHFollowUpBS" Category="" ClassName="CareConnect.Service.SDoHFollowUpBS" PoolSize="1" Enabled="true" Foreground="false" InactivityTimeout="0">
    <Setting Target="Host" Name="TargetConfigNames">CareConnect.Process.SDoHFollowUpBP</Setting>
  </Item>
  <Item Name="CareConnect.Process.SDoHFollowUpBP" Category="" ClassName="CareConnect.Process.SDoHFollowUpBP" PoolSize="1" Enabled="true" Foreground="false">
  </Item>
  <Item Name="CareConnect.Operation.SDoHFollowUpBO" Category="" ClassName="CareConnect.Operation.SDoHFollowUpBO" PoolSize="1" Enabled="true" Foreground="false">
  </Item>
</Production>
}

}
