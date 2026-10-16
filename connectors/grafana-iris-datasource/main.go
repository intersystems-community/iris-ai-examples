// Command grafana-iris-datasource is the backend process for the
// InterSystems IRIS Grafana data source plugin. Grafana's plugin loader
// launches this binary and communicates with it over gRPC using
// grafana-plugin-sdk-go; see pkg/plugin for the actual datasource logic.
package main

import (
	"os"

	"github.com/grafana/grafana-plugin-sdk-go/backend/datasource"
	"github.com/grafana/grafana-plugin-sdk-go/backend/log"

	"github.com/intersystems-community/iris-ai-examples/connectors/grafana-iris-datasource/pkg/plugin"
)

func main() {
	if err := datasource.Manage("intersystems-iris-datasource", plugin.NewDatasource, datasource.ManageOpts{}); err != nil {
		log.DefaultLogger.Error("iris datasource plugin exited with error", "error", err)
		os.Exit(1)
	}
}
