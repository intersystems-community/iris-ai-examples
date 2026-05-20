#!/bin/bash
SETUP_FLAG="/tmp/.careconnect-ready"

if [ ! -f "$SETUP_FLAG" ]; then
    echo "Waiting for IRIS superserver..."
    for i in $(seq 1 30); do
        if bash -c "cat < /dev/null > /dev/tcp/localhost/1972" 2>/dev/null; then
            break
        fi
        sleep 2
    done
    sleep 3

    cat > /tmp/startup.script << 'IRISEOF'
zn "USER"
set mgr = ##class(%AI.ToolMgr).GetOrCreate("/mcp/careconnect",.isNew)
do mgr.Cleanup()
set mgr = ##class(%AI.ToolMgr).GetOrCreate("/mcp/careconnect",.isNew)
do ##class(%AI.MCP.Service).LoadToolSetsToManager(mgr,"CareConnect.Tools.SDoHToolSet")
write "Tools: ",mgr.FindTools("").%Size(),!
do ##class(Ens.Director).StartProduction("CareConnect.Production")
write "Ready",!
halt
IRISEOF
    /usr/irissys/bin/irissession IRIS < /tmp/startup.script
    touch "$SETUP_FLAG"
fi

exec /iris-main "$@"
