Include %AI

Class KGTicketResolver.Tools.ToolSet Extends %AI.ToolSet
{

XData Definition
{
<ToolSet>
  <Description>KGTicketResolver tools for support ticket knowledge mining</Description>
  <Tool Name="ScoreTicketCompleteness" Method="ScoreTicketCompleteness">
    <Description>MDS score for a ticket. Pass ticketId like PC-00001. Returns 0-100 score and tier.</Description>
  </Tool>

  <Tool Name="FindSimilarTickets" Method="FindSimilarTickets">
    <Description>Semantic search. Pass query string. Returns similar ticket IDs and categories.</Description>
  </Tool>

  <Tool Name="GetClusterSummary" Method="GetClusterSummary">
    <Description>Cluster stats for a category. Pass category like BILLING. Shows anchor tickets and unresolved count.</Description>
  </Tool>

  <Tool Name="DraftKBArticle" Method="DraftKBArticle">
    <Description>Draft KB article from a cluster using AI Hub agent. Pass category. Returns structured article.</Description>
  </Tool>

  <Tool Name="GetWikiStatus" Method="GetWikiStatus">
    <Description>Wiki status and ticket coverage by category.</Description>
  </Tool>

  <Tool Name="PublishKBArticle" Method="PublishKBArticle">
    <Description>Publish KB article to wiki. Pass category, articleText, sourceTickets. Records provenance in Graph_KG.</Description>
  </Tool>

</ToolSet>
}

ClassMethod ScoreTicketCompleteness(ticketId As %String) As %String
{
    Set stmt = ##class(%SQL.Statement).%New()
    Do stmt.%Prepare("SELECT TicketId, Category, Summary, Problem, Solution, Status FROM KGTicketResolver_Ticket.Record WHERE TicketId = ?")
    Set rs = stmt.%Execute(ticketId)
    If rs.%Next() = 0 {
        Quit "Ticket not found: "_ticketId_". Use FindSimilarTickets to discover valid IDs."
    }
    Set score = 0
    If rs.Summary '= "" { Set score = score + 20 }
    If rs.Problem '= "" { Set score = score + 30 }
    If rs.Solution '= "" { Set score = score + 35 }
    If rs.Category '= "" { Set score = score + 10 }
    If rs.Status '= "" { Set score = score + 5 }
    Set tier = "LOW"
    If score >= 50 { Set tier = "MEDIUM" }
    If score >= 80 { Set tier = "HIGH" }
    Quit "MDS Score for "_ticketId_": "_score_"/100 | Tier: "_tier_" | Category: "_rs.Category_" | Status: "_rs.Status
}

ClassMethod FindSimilarTickets(query As %String, topK As %Integer = 8) As %String
{
    Set out = "Similar tickets for: """_query_""""_$Char(10)
    Set count = 0

    Set vecCheck = ##class(%SQL.Statement).%ExecDirect(,"SELECT COUNT(*) ct FROM KGTicketResolver_Ticket.Record WHERE SummaryVec IS NOT NULL")
    Set hasVectors = (vecCheck.%Next() && (vecCheck.%Get("ct") > 0))

    If hasVectors {
        Set queryVec = ..EmbedText(query)
        If queryVec '= "" {
            Set stmt = ##class(%SQL.Statement).%New()
            Do stmt.%Prepare("SELECT TOP ? TicketId, Category, Summary, HasSolution, VECTOR_COSINE(SummaryVec, TO_VECTOR(?,DOUBLE)) sim FROM KGTicketResolver_Ticket.Record WHERE SummaryVec IS NOT NULL ORDER BY sim DESC")
            Set rs = stmt.%Execute(topK, queryVec)
            While rs.%Next() {
                Set count = count + 1
                Set res = $Select(rs.HasSolution:"+ has resolution", 1:"  unresolved")
                Set sim = $Number(rs.%Get("sim"), 3)
                Set out = out_count_". "_rs.TicketId_" ["_rs.Category_"] "_res_" (sim="_sim_")"_$Char(10)_"   "_$Extract(rs.Summary,1,80)_$Char(10)
            }
            If count > 0 { Quit out_"[vector search]" }
        }
    }

    Set searchTerm = $ZConvert($Piece(query," ",1),"L")
    Set stmt = ##class(%SQL.Statement).%New()
    Do stmt.%Prepare("SELECT TOP ? TicketId, Category, Summary, HasSolution FROM KGTicketResolver_Ticket.Record WHERE LOWER(Summary) [ ? OR LOWER(Problem) [ ? OR UPPER(Category) = UPPER(?) ORDER BY HasSolution DESC, TicketId")
    Set rs = stmt.%Execute(topK, searchTerm, searchTerm, $ZConvert(query,"U"))
    Set count = 0
    While rs.%Next() {
        Set count = count + 1
        Set res = $Select(rs.HasSolution:"+ has resolution", 1:"  unresolved")
        Set out = out_count_". "_rs.TicketId_" ["_rs.Category_"] "_res_$Char(10)_"   "_$Extract(rs.Summary,1,80)_$Char(10)
    }
    If count = 0 { Quit "No similar tickets found for: "_query }
    Quit out_"[keyword search]"
}

ClassMethod EmbedText(text As %String) As %String
{
    Set apiKey = $System.Util.GetEnviron("OPENAI_API_KEY")
    If apiKey = "" { Quit "" }
    Set truncated = $Extract(text, 1, 512)
    Set body = {"model":"text-embedding-3-small","input":(truncated)}
    Set req = ##class(%Net.HttpRequest).%New()
    Set req.Server = "api.openai.com"
    Set req.Port = 443
    Set req.Https = 1
    Do req.SetHeader("Authorization", "Bearer "_apiKey)
    Do req.SetHeader("Content-Type", "application/json")
    Do req.EntityBody.Write(body.%ToJSON())
    Set sc = req.Post("/v1/embeddings")
    If $$$ISERR(sc) { Quit "" }
    Set resp = ##class(%DynamicObject).%FromJSON(req.HttpResponse.Data)
    Set vec = resp.%Get("data").%Get(0).%Get("embedding")
    If vec = "" { Quit "" }
    Set parts = ""
    Set iter = vec.%GetIterator()
    While iter.%GetNext(.k, .v) {
        Set parts = parts_$Select(parts="":"", 1:",")_v
    }
    Quit parts
}

ClassMethod GetClusterSummary(category As %String) As %String
{
    Set stmt = ##class(%SQL.Statement).%New()
    Do stmt.%Prepare("SELECT COUNT(*) Total, SUM(HasSolution) Resolved FROM KGTicketResolver_Ticket.Record WHERE UPPER(Category) = UPPER(?)")
    Set rs = stmt.%Execute(category)
    If rs.%Next() = 0 || (rs.Total = 0) {
        Quit "No tickets for category: "_category_". Valid: BILLING, LABORATORY, PHARMACY, PRINTING, INTERFACING, WAITING_LISTS, QUESTIONNAIRES"
    }
    Set total = rs.Total
    Set resolved = rs.Resolved
    Set pct = 0
    If total > 0 { Set pct = $Number(resolved/total*100, 0) }
    Set out = "Cluster: "_category_" | Total: "_total_" | Resolved: "_resolved_" ("_pct_"%)"_$Char(10)
    Do stmt.%Prepare("SELECT TOP 4 TicketId, Summary, Solution FROM KGTicketResolver_Ticket.Record WHERE UPPER(Category)=UPPER(?) AND HasSolution=1 ORDER BY TicketId")
    Set rs = stmt.%Execute(category)
    Set out = out_"Anchor tickets (resolved):"_$Char(10)
    While rs.%Next() {
        Set out = out_"  "_rs.TicketId_": "_$Extract(rs.Summary,1,70)_$Char(10)
        Set out = out_"    Fix: "_$Extract(rs.Solution,1,100)_$Char(10)
    }
    Do stmt.%Prepare("SELECT TOP 3 TicketId, Summary FROM KGTicketResolver_Ticket.Record WHERE UPPER(Category)=UPPER(?) AND HasSolution=0 ORDER BY TicketId")
    Set rs = stmt.%Execute(category)
    Set out = out_"Unresolved candidates:"_$Char(10)
    While rs.%Next() {
        Set out = out_"  "_rs.TicketId_": "_$Extract(rs.Summary,1,80)_$Char(10)
    }
    Set out = out_"Use DraftKBArticle("""_category_""") to generate a KB article."
    Quit out
}

ClassMethod DraftKBArticle(category As %String, maxTickets As %Integer = 5) As %String
{
    Set stmt = ##class(%SQL.Statement).%New()
    Do stmt.%Prepare("SELECT TOP ? TicketId, Summary, Problem, Solution FROM KGTicketResolver_Ticket.Record WHERE UPPER(Category)=UPPER(?) AND HasSolution=1 ORDER BY TicketId")
    Set rs = stmt.%Execute(maxTickets, category)
    Set context = ""
    Set count = 0
    While rs.%Next() {
        Set count = count + 1
        Set context = context_"Ticket "_rs.TicketId_":"_$Char(10)
        Set context = context_"Problem: "_$Extract(rs.Problem,1,200)_$Char(10)
        Set context = context_"Resolution: "_$Extract(rs.Solution,1,200)_$Char(10,10)
    }
    If count = 0 { Quit "No resolved tickets for: "_category_". Run GetClusterSummary first." }
    Set apiKey = $System.Util.GetEnviron("OPENAI_API_KEY")
    If apiKey = "" { Quit "OPENAI_API_KEY not set. Cannot draft KB article." }
    Set settings = {}
    Do settings.%Set("api_key", apiKey)
    Set provider = ##class(%AI.Provider).Create("openai", settings)
    Set agent = ##class(%AI.Agent).%New(provider)
    Set agent.Model = "gpt-4o-mini"
    Set agent.SystemPrompt = "You are a PlanetCare EMR KB writer. Write concise, actionable articles."
    Do agent.%Init()
    Set session = agent.CreateSession()
    Set prompt = "Write a KB article (Title, Problem, Root Cause, Resolution Steps, Prevention) from these "_category_" tickets:"_$Char(10)_context
    Set response = agent.Chat(session, prompt)
    Quit "KB ARTICLE -- "_category_$Char(10)_"---"_$Char(10)_response.Content_$Char(10)_"---"_$Char(10)_"Use PublishKBArticle() to publish after review."
}

ClassMethod GetWikiStatus() As %String
{
    Set wikiDir = $Select($System.Util.GetEnviron("WIKI_DIR")'="":$System.Util.GetEnviron("WIKI_DIR"),1:"/app/wiki/")
    Set out = "PlanetCare KB Wiki"_$Char(10)
    // Check for known wiki files
    Set knownFiles = $ListBuild("billing.md","laboratory.md","pharmacy.md")
    Set ptr = 0
    Set found = 0
    While $ListNext(knownFiles, ptr, fname) {
        If ##class(%Library.File).Exists(wikiDir_fname) {
            Set found = found + 1
            Set out = out_"  "_fname_$Char(10)
        }
    }
    If found = 0 { Set out = out_"  No wiki articles found in "_wikiDir_$Char(10) }
    Set out = out_$Char(10)_"Coverage:"_$Char(10)
    Set stmt = ##class(%SQL.Statement).%New()
    Do stmt.%Prepare("SELECT Category, COUNT(*) Total, SUM(HasSolution) Resolved FROM KGTicketResolver_Ticket.Record GROUP BY Category ORDER BY Total DESC")
    Set rs = stmt.%Execute()
    While rs.%Next() {
        Set pct = 0
        If rs.Total > 0 { Set pct = $Number(rs.Resolved/rs.Total*100, 0) }
        Set out = out_"  "_$Extract(rs.Category_"                    ",1,22)_rs.Resolved_"/"_rs.Total_" ("_pct_"%)"_$Char(10)
    }
    Quit out
}

ClassMethod PublishKBArticle(category As %String, articleText As %String, sourceTickets As %String = "") As %String
{
    Set ts = $ZDateTime($H, 3)
    Set slug = $ZCONVERT($REPLACE(category," ","_"),"L")
    Set articleId = "KB-PC-"_$ZCVT(slug,"U")
    Set wikiDir = $Select($System.Util.GetEnviron("WIKI_DIR")'="":$System.Util.GetEnviron("WIKI_DIR"),1:"/app/wiki/")
    Set wikiFile = wikiDir_slug_".md"
    Set section = $Char(10)_"---"_$Char(10,10)_"## "_articleId_" (AI-Generated "_ts_")"_$Char(10,10)_articleText_$Char(10,10)_"---"_$Char(10)
    If ##class(%File).Exists(wikiFile) {
        Set stream = ##class(%Stream.FileCharacter).%New()
        Set stream.Filename = wikiFile
        Do stream.MoveToEnd()
        Do stream.Write(section)
        Do stream.%Save()
        Set action = "augmented"
    } Else {
        Set stream = ##class(%Stream.FileCharacter).%New()
        Set stream.Filename = wikiFile
        Do stream.Write("# "_category_" -- PlanetCare KB"_$Char(10,10)_section)
        Do stream.%Save()
        Set action = "created"
    }
    Set stmt = ##class(%SQL.Statement).%New()
    Do stmt.%Prepare("INSERT INTO Graph_KG.rdf_props (s, key, val) VALUES (?,?,?)")
    Do stmt.%Execute("kb_article:"_articleId, "article_id", articleId)
    Do stmt.%Execute("kb_article:"_articleId, "category", category)
    Do stmt.%Execute("kb_article:"_articleId, "generated_at", ts)
    Do stmt.%Prepare("INSERT INTO Graph_KG.rdf_edges (s, p, o_id) VALUES (?,?,?)")
    Do stmt.%Execute("agent:KGTicketResolver.Tools.ToolSet", "AUTHORED_KB", "kb_article:"_articleId)
    If sourceTickets '= "" {
        Set i = 1
        While $Piece(sourceTickets,",",i) '= "" {
            Do stmt.%Execute("pc_ticket:"_$ZStrip($Piece(sourceTickets,",",i),"<>W"), "SOURCED_KB", "kb_article:"_articleId)
            Set i = i + 1
        }
    }
    Quit "Wiki "_action_": "_wikiFile_$Char(10)_"Article ID: "_articleId_$Char(10)_"Provenance in Graph_KG."
}

}
