/// KGTicketResolver Ticket Record
///
/// Persistent class holding the 276 synthetic PlanetCare EMR support tickets.
/// Seeded by KGTicketResolver.Setup.DemoData.Load()
Class KGTicketResolver.Ticket.Record Extends %Persistent
{

Property TicketId As %String(MAXLEN = 20) [ Required ];
Property Category As %String(MAXLEN = 50);
Property Hospital As %String(MAXLEN = 100);
Property Summary As %String(MAXLEN = 500);
Property Problem As %String(MAXLEN = 3000);
Property Solution As %String(MAXLEN = 2000);
Property Status As %String(MAXLEN = 20);
Property HasSolution As %Boolean;
Property FullContent As %String(MAXLEN = 4000);

Index TicketIdIdx On TicketId [ Unique ];
Index CategoryIdx On Category;
Index HasSolutionIdx On HasSolution;

Storage Default
{
<Data name="RecordDefaultData">
<Value name="1"><Value>%%CLASSNAME</Value></Value>
<Value name="2"><Value>TicketId</Value></Value>
<Value name="3"><Value>Category</Value></Value>
<Value name="4"><Value>Hospital</Value></Value>
<Value name="5"><Value>Summary</Value></Value>
<Value name="6"><Value>Problem</Value></Value>
<Value name="7"><Value>Solution</Value></Value>
<Value name="8"><Value>Status</Value></Value>
<Value name="9"><Value>HasSolution</Value></Value>
<Value name="10"><Value>FullContent</Value></Value>
</Data>
<DataLocation>^KGTicketResolver.Ticket.RecordD</DataLocation>
<DefaultData>RecordDefaultData</DefaultData>
<IdLocation>^KGTicketResolver.Ticket.RecordD</IdLocation>
<IndexLocation>^KGTicketResolver.Ticket.RecordI</IndexLocation>
<StreamLocation>^KGTicketResolver.Ticket.RecordS</StreamLocation>
<Type>%Storage.Persistent</Type>
</Storage>

}
