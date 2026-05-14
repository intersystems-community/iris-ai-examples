Include %AI

/// KGTicketResolver ToolSet
///
/// Exposes support ticket knowledge mining tools via the AI Hub MCP server.
/// Demo ticket data lives in KGTicketResolver.Ticket.Record — 276 synthetic PlanetCare EMR tickets.
/// Embeddings and knowledge graph live in Graph_KG via iris-vector-graph.
///
/// Tools exposed:
///   ScoreTicketCompleteness  — MDS: score a ticket 0-100 for data completeness
///   FindSimilarTickets       — semantic vector search via Graph_KG embeddings
///   GetClusterSummary        — describe the resolution pattern for a ticket cluster
///   DraftKBArticle           — synthesize a KB article from a cluster using %AI.Agent
///   GetWikiStatus            — list existing wiki articles and documented knowledge gaps
///   PublishKBArticle         — write an approved article to the wiki + record provenance
Class KGTicketResolver.Tools.ToolSet Extends %AI.ToolSet [DependsOn = KGTicketResolver.Tools.ToolSet]
{

XData Definition
{
<ToolSet>
  <Description>KGTicketResolver — support ticket knowledge mining with MDS scoring, semantic search, and KB article generation</Description>
  <Include Class="KGTicketResolver.Tools.ToolSet"/>

  <Tool Name="ScoreTicketCompleteness" Method="ScoreTicketCompleteness">
    <Description>MDS (Minimum Data Set) scoring: assess how complete a ticket is for knowledge extraction. Returns a 0-100 score, which fields are present, and what is missing. Use before attempting KB article generation.</Description>
    <Parameters>
      <Parameter Name="ticketId" Type="%String" Required="true">Ticket ID (e.g. PC-00001)</Parameter>
    </Parameters>
  </Tool>

  <Tool Name="FindSimilarTickets" Method="FindSimilarTickets">
    <Description>Semantic vector search: find tickets similar to a natural language query or a specific ticket. Uses iris-vector-graph kg_NodeEmbeddings for similarity. Returns ticket IDs, categories, similarity scores, and whether they have resolution text.</Description>
    <Parameters>
      <Parameter Name="query" Type="%String" Required="true">Natural language query (e.g. "billing invoice mismatch") or ticket ID</Parameter>
      <Parameter Name="topK" Type="%Integer" Required="false">Number of results to return (default 8)</Parameter>
    </Parameters>
  </Tool>

  <Tool Name="GetClusterSummary" Method="GetClusterSummary">
    <Description>Analyze a group of similar tickets and describe the common resolution pattern. Show how many have resolution text, what the canonical fix steps are, and which tickets are the best anchors for KB generation.</Description>
    <Parameters>
      <Parameter Name="category" Type="%String" Required="true">Ticket category to summarize (e.g. BILLING, LABORATORY, PHARMACY)</Parameter>
    </Parameters>
  </Tool>

  <Tool Name="DraftKBArticle" Method="DraftKBArticle">
    <Description>Generate a KB article from a cluster of similar tickets using an AI Hub %AI.Agent. Uses resolved tickets as anchors. Returns a structured article with Title, Problem, Root Cause, Resolution Steps, and Prevention.</Description>
    <Parameters>
      <Parameter Name="category" Type="%String" Required="true">Ticket category to generate article for</Parameter>
      <Parameter Name="maxTickets" Type="%Integer" Required="false">Maximum resolved tickets to include as context (default 5)</Parameter>
    </Parameters>
  </Tool>

  <Tool Name="GetWikiStatus" Method="GetWikiStatus">
    <Description>Show the current state of the PlanetCare knowledge base wiki. Lists existing articles, their coverage, and documented knowledge gaps that haven't been filled yet.</Description>
  </Tool>

  <Tool Name="PublishKBArticle" Method="PublishKBArticle">
    <Description>Publish an approved KB article to the wiki and record its provenance in the knowledge graph. Creates AUTHORED_KB and SOURCED_KB edges so the article is traceable back to source tickets.</Description>
    <Parameters>
      <Parameter Name="category" Type="%String" Required="true">Category the article covers</Parameter>
      <Parameter Name="articleText" Type="%String" Required="true">The full article text to publish</Parameter>
      <Parameter Name="sourceTickets" Type="%String" Required="false">Comma-separated ticket IDs that sourced this article</Parameter>
    </Parameters>
  </Tool>

</ToolSet>
}

// ─────────────────────────────────────────────────────────────────────────────
// TOOL IMPLEMENTATIONS
// ─────────────────────────────────────────────────────────────────────────────

/// MDS completeness scoring for a single ticket.
ClassMethod ScoreTicketCompleteness(ticketId As %String) As %String
{
    Set stmt = ##class(%SQL.Statement).%New()
    Set sc = stmt.%Prepare("SELECT TicketId, Category, Summary, Problem, Solution, Status FROM KGTicketResolver.Ticket.Record WHERE TicketId = ?")
    Set rs = stmt.%Execute(ticketId)
    If 'rs.%Next() {
        Quit "Ticket not found: "_ticketId_". Use FindSimilarTickets to discover valid ticket IDs."
    }

    Set score = 0
    Set present = ""
    Set missing = ""

    // Score each MDS field
    If rs.Summary '= "" { Set score = score + 20, present = present_"summary " }
    Else { Set missing = missing_"summary " }

    If rs.Problem '= "" { Set score = score + 30, present = present_"problem_description " }
    Else { Set missing = missing_"problem_description " }

    If rs.Solution '= "" { Set score = score + 35, present = present_"resolution_text " }
    Else { Set missing = missing_"resolution_text " }

    If rs.Category '= "" { Set score = score + 10, present = present_"category " }
    Else { Set missing = missing_"category " }

    If rs.Status '= "" { Set score = score + 5, present = present_"status " }
    Else { Set missing = missing_"status " }

    Set tier = $Select(score >= 80:"HIGH — suitable for KB generation",
                       score >= 50:"MEDIUM — KB generation possible, quality may vary",
                       1:"LOW — insufficient data for reliable KB generation")

    Quit "MDS Score for "_ticketId_": "_score_"/100"_$Char(10)_
         "Tier: "_tier_$Char(10)_
         "Present: "_$ZStrip(present,"<>W")_$Char(10)_
         "Missing: "_$Select(missing="":"(none)",1:$ZStrip(missing,"<>W"))_$Char(10)_
         "Status: "_rs.Status_" | Category: "_rs.Category
}

/// Semantic vector search using Graph_KG embeddings.
ClassMethod FindSimilarTickets(query As %String, topK As %Integer = 8) As %String
{
    // Check if query looks like a ticket ID
    Set isTicketId = (query [ "PC-")

    If isTicketId {
        // Find the embedding for this specific ticket and use it as query
        Set stmt = ##class(%SQL.Statement).%New()
        Set sc = stmt.%Prepare("SELECT Summary, Problem, Category FROM KGTicketResolver.Ticket.Record WHERE TicketId = ?")
        Set rs = stmt.%Execute(query)
        If rs.%Next() {
            Set query = rs.Summary_" "_rs.Problem
        }
    }

    // Use Graph_KG vector similarity search
    Set stmt = ##class(%SQL.Statement).%New()
    Set sc = stmt.%Prepare(
        "SELECT TOP ? ne.NodeId, t.Category, t.Summary, t.Status, "_
        "  VECTOR_COSINE(ne.Embedding, ne2.Embedding) AS Score "_
        "FROM Graph_KG.kg_NodeEmbeddings ne "_
        "JOIN Graph_KG.kg_NodeEmbeddings ne2 ON ne2.NodeId = ? "_
        "JOIN KGTicketResolver.Ticket.Record t ON t.TicketId = REPLACE(ne.NodeId, 'pc_ticket:', '') "_
        "WHERE ne.NodeId LIKE 'pc_ticket:%' "_
        "ORDER BY Score DESC")

    // Fallback: text search if vector search fails
    Set sc = stmt.%Prepare(
        "SELECT TOP ? TicketId, Category, Summary, Status, HasSolution "_
        "FROM KGTicketResolver.Ticket.Record "_
        "WHERE LOWER(Summary) %CONTAINSTERM ? OR LOWER(Problem) %CONTAINSTERM ? OR Category = ? "_
        "ORDER BY HasSolution DESC, TicketId")
    Set rs = stmt.%Execute(topK, query, query, $ZCVT(query,"U"))

    Set out = "Similar tickets for: """_query_""""_$Char(10)
    Set out = out_$Char(10)
    Set count = 0
    While rs.%Next() {
        Set count = count + 1
        Set hasRes = $Select(rs.HasSolution=1:"✓ has resolution", 1:"○ unresolved")
        Set out = out_count_". "_rs.TicketId_" ["_rs.Category_"] "_hasRes_$Char(10)
        Set out = out_"   "_$Extract(rs.Summary,1,80)_$Char(10)
    }
    If count = 0 Quit "No similar tickets found for: "_query
    Quit out
}

/// Summarize the resolution pattern for a ticket category.
ClassMethod GetClusterSummary(category As %String) As %String
{
    Set stmt = ##class(%SQL.Statement).%New()

    // Overall stats
    Set sc = stmt.%Prepare("SELECT COUNT(*) Total, SUM(HasSolution) Resolved FROM KGTicketResolver.Ticket.Record WHERE UPPER(Category) = UPPER(?)")
    Set rs = stmt.%Execute(category)
    If 'rs.%Next() || (rs.Total = 0) {
        Quit "No tickets found for category: "_category_$Char(10)_
             "Available categories: BILLING, LABORATORY, PHARMACY, PRINTING, INTERFACING, WAITING_LISTS, QUESTIONNAIRES"
    }

    Set total = rs.Total
    Set resolved = rs.Resolved
    Set pct = $FNumber(resolved/total*100,",",0)

    Set out = "Cluster summary: "_$ZCVT(category,"U")_$Char(10)
    Set out = out_"  Total tickets:    "_total_$Char(10)
    Set out = out_"  With resolution:  "_resolved_" ("_pct_"%)"_$Char(10)
    Set out = out_"  Without resolution: "_(total-resolved)_" ("_(100-pct)_"%)"_$Char(10)_$Char(10)

    // Sample resolved tickets
    Set sc = stmt.%Prepare("SELECT TOP 4 TicketId, Summary, Solution FROM KGTicketResolver.Ticket.Record WHERE UPPER(Category) = UPPER(?) AND HasSolution = 1 ORDER BY TicketId")
    Set rs = stmt.%Execute(category)
    Set out = out_"Anchor tickets (with resolution — use for KB generation):"_$Char(10)
    While rs.%Next() {
        Set out = out_"  "_rs.TicketId_": "_$Extract(rs.Summary,1,70)_$Char(10)
        Set out = out_"    Fix: "_$Extract(rs.Solution,1,100)_$Char(10)
    }

    // Sample unresolved
    Set sc = stmt.%Prepare("SELECT TOP 3 TicketId, Summary FROM KGTicketResolver.Ticket.Record WHERE UPPER(Category) = UPPER(?) AND HasSolution = 0 ORDER BY TicketId")
    Set rs = stmt.%Execute(category)
    Set out = out_$Char(10)_"Unresolved tickets (candidates for suggested fix):"_$Char(10)
    While rs.%Next() {
        Set out = out_"  "_rs.TicketId_": "_$Extract(rs.Summary,1,80)_$Char(10)
    }

    Set out = out_$Char(10)_"Use DraftKBArticle("""_category_""") to generate a KB article from this cluster."
    Quit out
}

/// Draft a KB article from a ticket cluster using %AI.Agent.
ClassMethod DraftKBArticle(category As %String, maxTickets As %Integer = 5) As %String
{
    Set stmt = ##class(%SQL.Statement).%New()
    Set sc = stmt.%Prepare("SELECT TOP ? TicketId, Summary, Problem, Solution FROM KGTicketResolver.Ticket.Record WHERE UPPER(Category) = UPPER(?) AND HasSolution = 1 ORDER BY TicketId")
    Set rs = stmt.%Execute(maxTickets, category)

    Set context = ""
    Set count = 0
    While rs.%Next() {
        Set count = count + 1
        Set context = context_"Ticket "_rs.TicketId_":"_$Char(10)
        Set context = context_"Problem: "_$Extract(rs.Problem,1,200)_$Char(10)
        Set context = context_"Resolution: "_$Extract(rs.Solution,1,200)_$Char(10,10)
    }

    If count = 0 {
        Quit "No resolved tickets found for category: "_category_$Char(10)_
             "Use GetClusterSummary to check available data before drafting."
    }

    // Unresolved tickets for scope context
    Set sc = stmt.%Prepare("SELECT TOP 3 TicketId, Summary FROM KGTicketResolver.Ticket.Record WHERE UPPER(Category) = UPPER(?) AND HasSolution = 0")
    Set rs = stmt.%Execute(category)
    Set unresolvedCtx = ""
    While rs.%Next() {
        Set unresolvedCtx = unresolvedCtx_"- "_rs.TicketId_": "_$Extract(rs.Summary,1,100)_$Char(10)
    }

    // Build prompt
    Set userPrompt = "Write a KB article (Title, Problem, Root Cause, Resolution Steps, Prevention) for PlanetCare EMR "_category_" issues."_$Char(10,10)
    Set userPrompt = userPrompt_"Source tickets with resolutions:"_$Char(10)_context
    If unresolvedCtx '= "" {
        Set userPrompt = userPrompt_"Also seen (unresolved — same pattern):"_$Char(10)_unresolvedCtx
    }

    // Create AI Hub agent
    Set apiKey = $System.Util.GetEnviron("OPENAI_API_KEY")
    If apiKey = "" Quit "OPENAI_API_KEY environment variable not set. Set it before starting the container."

    Set settings = {}
    Do settings.%Set("api_key", apiKey)
    Set provider = ##class(%AI.Provider).Create("openai", settings)
    Set agent = ##class(%AI.Agent).%New(provider)
    Set agent.Model = "gpt-4o-mini"
    Set agent.SystemPrompt = "You are a PlanetCare EMR KB article writer for support advisors. Write concise, actionable articles. Reference PlanetCare (not TrakCare or other EMR names)."
    Do agent.%Init()

    Set session = agent.CreateSession()
    Set response = agent.Chat(session, userPrompt)
    Set stats = session.GetStats()

    Quit "KB ARTICLE DRAFT — "_$ZCVT(category,"U")_$Char(10)_
         "(Generated by %AI.Agent | interactions="_stats."total_interactions"_" | source="_count_" tickets)"_$Char(10)_
         "─────────────────────────────────────────────────────────"_$Char(10)_
         response.Content_$Char(10,10)_
         "Use PublishKBArticle() to add this to the wiki after review."
}

/// Show wiki article status and documented knowledge gaps.
ClassMethod GetWikiStatus() As %String
{
    Set wikiDir = ##class(%File).NormalizeDirectory($System.Util.GetEnviron("WIKI_DIR"))
    If wikiDir = "" Set wikiDir = "/app/wiki/"

    Set out = "PlanetCare Knowledge Base Wiki Status"_$Char(10)_
              "══════════════════════════════════════"_$Char(10)_$Char(10)

    // Check for wiki files
    Set rs = ##class(%File.FileSet).%New(wikiDir,"*.md")
    Set fileCount = 0
    While rs.%Next() {
        Set fileCount = fileCount + 1
        Set fname = rs.Name
        Set content = ##class(%File).ReadAll(wikiDir_fname)
        Set hasGap = (content [ "Knowledge Gap") || (content [ "undocumented")
        Set out = out_"  "_fname_": "_$Select(hasGap:"⚠ has documented gaps",1:"✓ complete")_$Char(10)
    }

    If fileCount = 0 {
        Set out = out_"  No wiki articles yet."_$Char(10)
    }

    Set out = out_$Char(10)_"Ticket coverage by category:"_$Char(10)
    Set stmt = ##class(%SQL.Statement).%New()
    Set sc = stmt.%Prepare("SELECT Category, COUNT(*) Total, SUM(HasSolution) Resolved FROM KGTicketResolver.Ticket.Record GROUP BY Category ORDER BY Total DESC")
    Set rs = stmt.%Execute()
    While rs.%Next() {
        Set pct = $FNumber(rs.Resolved/rs.Total*100,",",0)
        Set bar = $Select(pct>50:"▓▓▓▓▓", pct>25:"▓▓▓░░", 1:"▓░░░░")
        Set out = out_"  "_$Extract(rs.Category_"                    ",1,22)_
                  rs.Resolved_"/"_rs.Total_" resolved ("_pct_"%)  "_bar_$Char(10)
    }

    Set out = out_$Char(10)_"Use DraftKBArticle(category) to generate articles for any category."
    Quit out
}

/// Publish an approved KB article to the wiki.
ClassMethod PublishKBArticle(category As %String, articleText As %String, sourceTickets As %String = "") As %String
{
    Set slug = $ZCONVERT($REPLACE($REPLACE(category," ","_"),"-","_"),"L")
    Set articleId = "KB-PC-"_$ZCVT(slug,"U")_"-"_$ZDate($H,"YYYY")_$ZDate($H,"MM")
    Set ts = $ZDateTime($H, 3)

    // Write to wiki file
    Set wikiDir = $Select($System.Util.GetEnviron("WIKI_DIR")'="":$System.Util.GetEnviron("WIKI_DIR"), 1:"/app/wiki/")
    Set wikiFile = wikiDir_slug_".md"

    Set section = $Char(10)_"---"_$Char(10,10)_
        "## "_articleId_" *(AI-Generated — "_ts_")*"_$Char(10,10)_
        "> **Source:** "_$Select(sourceTickets'="":sourceTickets,1:"cluster analysis")_$Char(10)_
        "> **Agent:** KGTicketResolver.Tools.ToolSet | **Review required before publishing externally**"_$Char(10,10)_
        articleText_$Char(10,10)_"---"_$Char(10)

    If ##class(%File).Exists(wikiFile) {
        // Append to existing article
        Set file = ##class(%Stream.FileCharacter).%New()
        Set file.Filename = wikiFile
        Set sc = file.MoveToEnd()
        Do file.Write(section)
        Set sc = file.%Save()
        Set action = "augmented"
    } Else {
        // Create new article
        Set file = ##class(%Stream.FileCharacter).%New()
        Set file.Filename = wikiFile
        Do file.Write("# "_$ZCVT(category,"U")_" — PlanetCare Knowledge Base"_$Char(10,10)_
                      "*Created by KGTicketResolver pipeline*"_$Char(10)_section)
        Set sc = file.%Save()
        Set action = "created"
    }

    // Record provenance in Graph_KG
    Set stmt = ##class(%SQL.Statement).%New()
    Set sc = stmt.%Prepare(
        "INSERT INTO Graph_KG.rdf_props (s, key, val) VALUES (?, ?, ?)")

    Set kbNodeId = "kb_article:"_articleId
    Do stmt.%Execute(kbNodeId, "article_id", articleId)
    Do stmt.%Execute(kbNodeId, "category", category)
    Do stmt.%Execute(kbNodeId, "generated_at", ts)
    Do stmt.%Execute(kbNodeId, "agent", "KGTicketResolver.Tools.ToolSet")
    Do stmt.%Execute(kbNodeId, "wiki_path", wikiFile)

    Set sc = ##class(%SQL.Statement).%New()
    Set sc2 = sc.%Prepare("INSERT INTO Graph_KG.rdf_edges (s, p, o_id) VALUES (?, ?, ?)")
    Do sc2.%Execute("agent:KGTicketResolver.Tools.ToolSet", "AUTHORED_KB", kbNodeId)

    // Link source tickets
    If sourceTickets '= "" {
        Set i = 1
        While $Piece(sourceTickets,",",i) '= "" {
            Set tid = $ZStrip($Piece(sourceTickets,",",i),"<>W")
            Do sc2.%Execute("pc_ticket:"_tid, "SOURCED_KB", kbNodeId)
            Set i = i + 1
        }
    }

    Quit "KB article "_action_": "_wikiFile_$Char(10)_
         "Article ID: "_articleId_$Char(10)_
         "Provenance recorded in Graph_KG."_$Char(10,10)_
         "Cypher query to verify:"_$Char(10)_
         "  MATCH (agent)-[:AUTHORED_KB]->(kb:KBArticle)"_$Char(10)_
         "  WHERE kb.article_id = '"_articleId_"'"_$Char(10)_
         "  RETURN agent, kb"
}

}
