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
Property SummaryVec As %Vector(DATATYPE = "DOUBLE", LEN = 384);

Index TicketIdIdx On TicketId [ Unique ];
Index CategoryIdx On Category;
Index HasSolutionIdx On HasSolution;

}
