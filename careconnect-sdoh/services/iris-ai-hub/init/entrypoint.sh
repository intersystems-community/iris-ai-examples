#!/bin/bash

for i in $(seq 1 30); do
    bash -c 'cat < /dev/null > /dev/tcp/localhost/1972' 2>/dev/null && break
    sleep 3
done

SETUP_FLAG=/tmp/.careconnect-setup-done
SETUP_LOG=/tmp/careconnect-setup.log

# NOTE: irissession executes stdin one line at a time. Multi-line { } blocks are NOT
# executed as a unit — a `while ... {` line raises <SYNTAX> on its own and the body never
# runs. So every statement below stays on a single line, and directory loading goes through
# LoadDir rather than a read-a-file-and-loop script.
if [ ! -f "$SETUP_FLAG" ]; then
    echo "=== CareConnect first-time setup ==="

    if [ -d "/src/CareConnect" ]; then
        echo "Found $(find /src/CareConnect -name '*.cls' | wc -l | tr -d ' ') .cls files"

        cat > /tmp/init.script << 'IRISEOF'
; CareConnect.Production and the Message/Service/Process/Operation classes extend Ens.*,
; which is not visible in USER until Interoperability is enabled there. Without this the
; load stops at "Class 'Ens.Request' does not exist" and nothing after it compiles.
zn "%SYS"
do ##class(%EnsembleMgr).EnableNamespace("USER",1)
zn "USER"
do $system.OBJ.LoadDir("/src/CareConnect","ck",.err,1)
do $system.OBJ.Compile("CareConnect.Tools.SDoHToolSet","ck")
do ##class(CareConnect.Setup.Roles).CreateAll()
; Report the endpoint the agents' PROVIDERCONFIG placeholders resolve to, and probe it.
; Replaces CareConnect.Setup.ConfigStore, which logged "openai entry created" while
; writing nothing — %AI.ConfigStore.Set() does not exist on this build.
do ##class(CareConnect.Setup.LLMConfig).Describe()
Write "LLM probe: ",##class(CareConnect.Setup.LLMConfig).Probe(),!
do ##class(CareConnect.Setup.DemoData).Load()
Write "Setup OK. MCP.Service: ",##class(%Dictionary.ClassDefinition).%ExistsId("CareConnect.MCP.Service"),!
Write "SDoHToolSet: ",##class(%Dictionary.ClassDefinition).%ExistsId("CareConnect.Tools.SDoHToolSet"),!
Write "Setup.Roles: ",##class(%Dictionary.ClassDefinition).%ExistsId("CareConnect.Setup.Roles"),!
Write "Production cls: ",##class(%Dictionary.ClassDefinition).%ExistsId("CareConnect.Production"),!
; Pre-populate wgproto discovery cache so iris-mcp-server GET /v1/services finds tools immediately
set mgr = ##class(%AI.ToolMgr).GetOrCreate("/mcp/careconnect", .isNew)
set sc = ##class(%AI.MCP.Service).LoadToolSetsToManager(mgr, "CareConnect.Tools.SDoHToolSet")
Write "Discovery cache populated (isNew=",isNew,"): ",$System.Status.IsOK(sc),!
; Start the CareConnect Interoperability production
set startSC = ##class(Ens.Director).StartProduction("CareConnect.Production")
Write "Production started: ",$System.Status.IsOK(startSC),!
halt
IRISEOF
        # tee, because a container's -a command writes where docker logs cannot see it.
        # Without the copy in $SETUP_LOG a failed setup leaves no trace at all, and the
        # healthcheck below still reports healthy.
        /usr/irissys/bin/irissession IRIS < /tmp/init.script 2>&1 | tee "$SETUP_LOG"
    fi

    if [ -d "/src/IIA" ]; then
        cat > /tmp/init_iia.script << 'IRISEOF'
zn "USER"
do $system.OBJ.LoadDir("/src/IIA","ck",.err,1)
halt
IRISEOF
        /usr/irissys/bin/irissession IRIS < /tmp/init_iia.script 2>&1 | tee -a "$SETUP_LOG"
    fi

    touch "$SETUP_FLAG"
    echo "=== Setup complete ==="
fi

tail -f /dev/null
