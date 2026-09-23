/// Lets AI Hub Service drive an Interoperability production on an IRIS that
/// predates AI Hub.
///
/// Load this one class into the legacy application's namespace. The service
/// calls it over the Native API (superserver, port 1972), so it works on any
/// IRIS version the Native API reaches. It depends on nothing newer than
/// %DynamicObject and Ens.Director: no %AI, no embedded Python, no
/// %JSON.Adaptor. tests/test_objectscript.py holds it to that.
///
/// Dispatch is allow-listed. The service can only reach business services an
/// administrator named in advance, with the request class named in advance:
///
///   Do ##class(AIHub.Legacy.Interop).Allow("CareConnect.Service.SDoHFollowUpBS",
///                                          "CareConnect.Message.FollowUpRequest")
///
/// Every method returns a string, because tools return text.
Class AIHub.Legacy.Interop Extends %RegisteredObject
{

/// Add one business service to the dispatch allow-list, bound to one request class.
ClassMethod Allow(serviceName As %String, requestClass As %String) As %Status
{
    If (serviceName = "") || (requestClass = "") Quit $System.Status.Error(5001, "serviceName and requestClass are required")
    Set ^AIHub.Config("dispatch", serviceName) = requestClass
    Quit $$$OK
}

/// Remove a business service from the dispatch allow-list.
ClassMethod Disallow(serviceName As %String) As %Status
{
    Kill ^AIHub.Config("dispatch", serviceName)
    Quit $$$OK
}

/// Build a request of <var>requestClass</var> from <var>propsJSON</var>, hand it to
/// business service <var>serviceName</var>, and return JSON:
///   {"status":"ok","service":...,"response":{...datatype properties...}}
///   {"status":"not_running","production":...}
///   {"status":"forbidden"|"error","error":...}
ClassMethod Dispatch(serviceName As %String, requestClass As %String, propsJSON As %String = "{}") As %String
{
    Set result = ##class(%DynamicObject).%New()
    Try {
        If $Get(^AIHub.Config("dispatch", serviceName)) '= requestClass {
            Set result.status = "forbidden"
            Set result.error = serviceName_" with "_requestClass_" is not on the dispatch allow-list. An administrator adds it with ##class(AIHub.Legacy.Interop).Allow()."
            Quit
        }
        Set sc = ##class(Ens.Director).GetProductionStatus(.prod, .state)
        If $$$ISERR(sc) {
            Set result.status = "error"
            Set result.error = $System.Status.GetErrorText(sc)
            Quit
        }
        If state '= 1 {
            Set result.status = "not_running"
            Set result.production = prod
            Quit
        }
        Set props = ##class(%DynamicObject).%FromJSON($Select(propsJSON = "": "{}", 1: propsJSON))
        Set request = $ClassMethod(requestClass, "%New")
        Set iter = props.%GetIterator()
        While iter.%GetNext(.key, .value) {
            Set $Property(request, key) = value
        }
        Set sc = ##class(Ens.Director).CreateBusinessService(serviceName, .service)
        If $$$ISERR(sc) {
            Set result.status = "error"
            Set result.error = "creating service: "_$System.Status.GetErrorText(sc)
            Quit
        }
        Set sc = service.ProcessInput(request, .response)
        If $$$ISERR(sc) {
            Set result.status = "error"
            Set result.error = "processing: "_$System.Status.GetErrorText(sc)
            Quit
        }
        Set result.status = "ok"
        Set result.service = serviceName
        Set result.response = ..Properties($Get(response))
    } Catch ex {
        Set result.status = "error"
        Set result.error = ex.DisplayString()
    }
    Quit result.%ToJSON()
}

/// The production's name, state and components, in the text SDoHToolSet's
/// GetProductionStatus prints.
ClassMethod ProductionStatus() As %String
{
    Set sc = ##class(Ens.Director).GetProductionStatus(.prodName, .state)
    If $$$ISERR(sc) Quit "ERROR: "_$System.Status.GetErrorText(sc)
    If prodName = "" Quit "No production configured in namespace "_$Namespace_"."
    Set stateText = $Case(state, 1:"Running", 2:"Stopped", 3:"Suspended", 4:"Troubled", :"Unknown("_state_")")
    Set out = "Production: "_prodName_$Char(10)_"Status: "_stateText_$Char(10)
    If state '= 1 Quit out
    Set stmt = ##class(%SQL.Statement).%New()
    Set sc = stmt.%Prepare("SELECT Name,Enabled FROM Ens_Config.Item WHERE Production=? ORDER BY Name")
    If $$$ISERR(sc) Quit out
    Set rs = stmt.%Execute(prodName)
    Set out = out_"Components:"_$Char(10)
    While rs.%Next() {
        Set out = out_"  "_rs.Name_": "_$Select(rs.Enabled: "Enabled", 1: "Disabled")_$Char(10)
    }
    Quit out
}

/// Start <var>productionName</var> unless a production is already running.
ClassMethod StartProduction(productionName As %String) As %String
{
    Set sc = ##class(Ens.Director).GetProductionStatus(.prod, .state)
    If $$$ISERR(sc) Quit "ERROR checking status: "_$System.Status.GetErrorText(sc)
    If state = 1 Quit "Production already running: "_prod
    Set sc = ##class(Ens.Director).StartProduction(productionName)
    If $$$ISERR(sc) Quit "ERROR starting production: "_$System.Status.GetErrorText(sc)
    Set sc = ##class(Ens.Director).GetProductionStatus(.prod, .state)
    Set stateText = $Case(state, 1:"Running", 2:"Stopped", 3:"Suspended", :"Unknown("_state_")")
    Quit "Production started: "_prod_" ("_stateText_")"
}

/// The public, single-valued datatype properties of <var>obj</var> as a %DynamicObject.
/// A reflection walk rather than %JSON.Adaptor, which older versions lack and
/// which the application's message classes would have to inherit.
ClassMethod Properties(obj) As %DynamicObject
{
    Set out = ##class(%DynamicObject).%New()
    If '$IsObject(obj) Quit out
    Set def = ##class(%Dictionary.CompiledClass).%OpenId($ClassName(obj))
    If '$IsObject(def) Quit out
    For i = 1:1:def.Properties.Count() {
        Set p = def.Properties.GetAt(i)
        Continue:($Extract(p.Name) = "%")||p.Private||p.MultiDimensional||(p.Collection '= "")
        Set typeDef = ##class(%Dictionary.CompiledClass).%OpenId(p.Type)
        Continue:'$IsObject(typeDef)
        Continue:(typeDef.ClassType '= "datatype")
        Do out.%Set(p.Name, $Property(obj, p.Name))
    }
    Quit out
}

}
