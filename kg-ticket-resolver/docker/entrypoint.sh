#!/bin/bash
SETUP_FLAG="/tmp/.kgtickets-ready"

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
do $system.OBJ.Delete("KGTicketResolver.Tools.ToolSet","k")
do $system.OBJ.Load("/src/KGTicketResolver/Tools/ToolSet.cls","k")
do $system.OBJ.Compile("KGTicketResolver.Tools.ToolSet","ck")
set mgr = ##class(%AI.ToolMgr).GetOrCreate("/mcp/kgtickets",.isNew)
do mgr.Cleanup()
set mgr = ##class(%AI.ToolMgr).GetOrCreate("/mcp/kgtickets",.isNew)
do ##class(%AI.MCP.Service).LoadToolSetsToManager(mgr,"KGTicketResolver.Tools.ToolSet")
write "Tools: ",mgr.FindTools("").%Size(),!
write "Ready",!
halt
IRISEOF
    /usr/irissys/bin/irissession IRIS < /tmp/startup.script
    touch "$SETUP_FLAG"
fi

exec /iris-main "$@"
