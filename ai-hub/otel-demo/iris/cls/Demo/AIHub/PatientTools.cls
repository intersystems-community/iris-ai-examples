Include (%AI, %occStatus)

/// Agent tool that reaches into the interoperability production. The tool body runs
/// inside an execute_tool span, so every interop span it causes nests under it.
Class Demo.AIHub.PatientTools Extends %AI.Tool
{

/// Look up a patient's clinical summary by patient ID.
ClassMethod LookupPatient(patientId As %String(DESCRIPTION="Patient identifier")) As %String
{
    // The doc comment above is the model-facing tool description, so the reason
    // lives here: the work runs in a worker job because %Trace inside the agent's
    // tool callback trips the kernel zfpop() bug (SIGSEGV in Cdzf; kernel fix
    // pending). The callback only hands off the execute_tool span's traceparent.
    Set tKey = $Increment(^IRIS.Temp.AIHubTool)
    Kill ^IRIS.Temp.AIHubTool(tKey)
    Job ##class(Demo.AIHub.PatientTools).RunLookup(tKey, patientId, ##class(%AI.Tool).CurrentTraceparent())::5
    If '$Test Return "{""error"": ""tool worker did not start""}"
    For tI = 1:1:300 { Quit:$Data(^IRIS.Temp.AIHubTool(tKey))  Hang 0.1 }
    Set tResult = $Get(^IRIS.Temp.AIHubTool(tKey), "{""error"": ""tool worker timed out""}")
    Kill ^IRIS.Temp.AIHubTool(tKey)
    Return tResult
}

/// Internal keeps this and Interop out of the agent's tool list.
/// Worker body: the interop call, parented on the Rust execute_tool span through
/// pParent. Result written to ^IRIS.Temp.AIHubTool(pKey).
ClassMethod RunLookup(pKey As %Integer, patientId As %String, pParent As %String) [ Internal ]
{
    Set ^IRIS.Temp.AIHubTool(pKey) = ..Interop(patientId, pParent)
}

/// The BS -> BP -> BO round trip. pParent, when set, becomes the parent of the
/// bs.ToolService span. Safe to call directly anywhere that is not inside an
/// %AI.Agent tool callback.
ClassMethod Interop(patientId As %String, pParent As %String = "") As %String [ Internal ]
{
    Set tResult = ""
    If pParent '= "" { Set ^IRIS.Temp.MsgTraceparent($Job) = pParent }
    Try {
        Set tSC = ##class(Ens.Director).CreateBusinessService("ToolService", .tService)
        $$$ThrowOnError(tSC)
        Set tReq = ##class(Demo.AIHub.PatientRequest).%New()
        Set tReq.PatientId = patientId
        Set tSC = tService.ProcessInput(tReq, .tResp)
        $$$ThrowOnError(tSC)
        Set tResult = tResp.Summary
    } Catch tEx {
        Set tResult = "{""error"": """_$ZConvert(tEx.DisplayString(), "O", "JSON")_"""}"
    }
    Kill ^IRIS.Temp.MsgTraceparent($Job)
    Quit tResult
}

}
