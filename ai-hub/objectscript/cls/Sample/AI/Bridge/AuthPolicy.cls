Include (%AI, %occStatus)

/// Authorization policy for bridge-compiled Python toolsets.
///
/// Provides a configurable allow/deny list at the tool name level
/// so operators can restrict which Python-defined tools the agent
/// may invoke, without modifying the ToolSet class itself.
///
/// Usage — attach to an agent before %Init():
///
///   Set tPolicy = ##class(Sample.AI.Bridge.AuthPolicy).%New()
///   // Deny specific tools by name
///   Do tPolicy.DenyList.Insert("count_classes")
///   // Or lock down to an explicit allow list (strict mode)
///   Do tPolicy.AllowList.Insert("get_iris_version")
///   Do tPolicy.AllowList.Insert("list_namespaces")
///   Set tPolicy.Strict = 1
///   Set tAgent.AuthorizationPolicy = tPolicy
///
/// Default (empty lists, Strict=0): all tools allowed.
Class Sample.AI.Bridge.AuthPolicy Extends %AI.Policy.Authorization
{

/// Tool names explicitly denied regardless of AllowList.
Property DenyList As list Of %String;

/// Tool names explicitly allowed. Only checked when Strict=1.
Property AllowList As list Of %String;

/// When 1, deny any tool not in AllowList.
Property Strict As %Boolean [ InitialExpression = 0 ];

Method %CanExecute(tool As %String, call As %DynamicObject, metadata As %DynamicObject) As %Status
{
    Set tSC = $$$OK

    // Explicit deny wins over everything
    For i=1:1:..DenyList.Count() {
        If ..DenyList.GetAt(i) = tool {
            Return $$$ERROR($$$AICoreToolAccessDenied, "Tool denied by bridge policy: " _ tool)
        }
    }

    // Strict mode: must appear in AllowList
    If ..Strict {
        Set tAllowed = 0
        For i=1:1:..AllowList.Count() {
            If ..AllowList.GetAt(i) = tool {
                Set tAllowed = 1
                Quit
            }
        }
        If 'tAllowed {
            Return $$$ERROR($$$AICoreToolAccessDenied, "Tool not in allow list: " _ tool)
        }
    }

    Return tSC
}

/// Called by the framework before listing tools to the LLM.
/// Returns 1 to include the tool in the prompt, 0 to hide it.
Method %CanList(tool As %String, metadata As %DynamicObject) As %Boolean
{
    // Hide denied tools from the tool listing so the LLM doesn't try to call them
    For i=1:1:..DenyList.Count() {
        If ..DenyList.GetAt(i) = tool { Return 0 }
    }
    If ..Strict && (..AllowList.Count() > 0) {
        For i=1:1:..AllowList.Count() {
            If ..AllowList.GetAt(i) = tool { Return 1 }
        }
        Return 0
    }
    Return 1
}

}
