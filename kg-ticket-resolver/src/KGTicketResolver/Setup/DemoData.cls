/// Loads 276 synthetic PlanetCare EMR support tickets into KGTicketResolver.Ticket.Record.
/// Safe to call multiple times — skips if data already present.
Class KGTicketResolver.Setup.DemoData Extends %RegisteredObject
{

ClassMethod Load() As %Status
{
    // Check if already loaded
    Set stmt = ##class(%SQL.Statement).%New()
    Set sc = stmt.%Prepare("SELECT COUNT(*) ct FROM KGTicketResolver.Ticket.Record")
    Set rs = stmt.%Execute()
    If rs.%Next() && (rs.ct > 0) {
        Write "Demo data already loaded (", rs.ct, " tickets).", !
        Quit $$$OK
    }

    // Load from JSON file bundled with the image
    Set dataFile = "/app/data/planetcare_demo_tickets.json"
    If '##class(%File).Exists(dataFile) {
        Write "Data file not found: ", dataFile, !
        Quit $$$ERROR($$$GeneralError, "Data file missing: "_dataFile)
    }

    Set stream = ##class(%Stream.FileCharacter).%New()
    Set stream.Filename = dataFile
    Set json = ""
    While 'stream.AtEnd {
        Set json = json_stream.Read(32768)
    }

    Set tickets = ##class(%DynamicArray).%FromJSON(json)
    Set iter = tickets.%GetIterator()
    Set inserted = 0
    Set ins = ##class(%SQL.Statement).%New()
    Set sc = ins.%Prepare(
        "INSERT INTO KGTicketResolver.Ticket.Record "_
        "(TicketId, Category, Hospital, Summary, Problem, Solution, Status, HasSolution, FullContent) "_
        "VALUES (?,?,?,?,?,?,?,?,?)")

    While iter.%GetNext(.idx, .ticket) {
        Set ticketId  = ticket.ticket_id
        Set category  = ticket.Classification
        Set hospital  = ticket.Hospital
        Set summary   = $Extract(ticket.Summary, 1, 500)
        Set problem   = $Extract(ticket.Problem, 1, 3000)
        Set solution  = $Extract(ticket.Solution, 1, 2000)
        Set status    = ticket.Status
        Set hasSol    = $Select(ticket.has_solution=1:1, ticket.has_solution="true":1, 1:0)
        Set fullText  = $Extract(summary_" "_problem, 1, 4000)

        Do ins.%Execute(ticketId, category, hospital, summary, problem, solution, status, hasSol, fullText)
        Set inserted = inserted + 1
    }

    Write "Loaded ", inserted, " PlanetCare tickets.", !
    Quit $$$OK
}

}
