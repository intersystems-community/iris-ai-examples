/// Loads 276 synthetic PlanetCare EMR support tickets into KGTicketResolver.Ticket.Record.
/// Safe to call multiple times -- skips if data already present.
Class KGTicketResolver.Setup.DemoData Extends %RegisteredObject
{

ClassMethod Load() As %Status
{
    // Check if already loaded
    Set stmt = ##class(%SQL.Statement).%New()
    Set sc = stmt.%Prepare("SELECT COUNT(*) ct FROM KGTicketResolver_Ticket.Record")
    Set rs = stmt.%Execute()
    Do rs.%Next()
    If rs.%Get("ct") > 0 {
        Write "Demo data already loaded (", rs.%Get("ct"), " tickets).", !
        Quit $$$OK
    }

    // Load from JSON file bundled with the image
    Set dataFile = "/app/data/planetcare_demo_tickets.json"
    If ##class(%Library.File).Exists(dataFile) = 0 {
        Write "Data file not found: ", dataFile, !
        Quit $$$ERROR($$$GeneralError, "Data file missing: "_dataFile)
    }

    // Read file
    Set stream = ##class(%Stream.FileCharacter).%New()
    Set stream.Filename = dataFile
    Set json = ""
    While stream.AtEnd = 0 {
        Set json = json_stream.Read(65536)
    }

    Set tickets = ##class(%DynamicArray).%FromJSON(json)
    Set iter = tickets.%GetIterator()
    Set inserted = 0

    Set ins = ##class(%SQL.Statement).%New()
    Set sc = ins.%Prepare("INSERT INTO KGTicketResolver_Ticket.Record (TicketId,Category,Hospital,Summary,Problem,Solution,Status,HasSolution,FullContent) VALUES (?,?,?,?,?,?,?,?,?)")

    While iter.%GetNext(.idx, .ticket) {
        Set ticketId = ticket.%Get("ticket_id")
        If ticketId = "" { Continue }
        Set category  = ticket.%Get("Classification")
        Set hospital  = ticket.%Get("Hospital")
        Set summary   = $Extract(ticket.%Get("Summary"), 1, 500)
        Set problem   = $Extract(ticket.%Get("Problem"), 1, 3000)
        Set solution  = $Extract(ticket.%Get("Solution"), 1, 2000)
        Set status    = ticket.%Get("Status")
        Set hasSol    = $Select(ticket.%Get("has_solution")=1:1, $ZCVT(ticket.%Get("has_solution"),"U")="TRUE":1, 1:0)
        Set fullText  = $Extract(summary_" "_problem, 1, 4000)

        Set rs2 = ins.%Execute(ticketId, category, hospital, summary, problem, solution, status, hasSol, fullText)
        If rs2.%SQLCODE >= 0 { Set inserted = inserted + 1 }
    }

    Write "Loaded ", inserted, " PlanetCare tickets.", !
    Quit $$$OK
}

}
