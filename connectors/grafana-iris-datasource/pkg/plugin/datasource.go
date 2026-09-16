// Package plugin implements the Grafana backend datasource for
// InterSystems IRIS: config parsing, query dispatch, health checks, and
// SQL/metrics-result-to-data.Frame conversion. It depends only on the
// client.IRISClient interface, never on a concrete transport, so the
// access path to IRIS (REST/SQL today) can be swapped or added to
// without touching this file. See pkg/plugin/client/client.go.
package plugin

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/grafana/grafana-plugin-sdk-go/backend"
	"github.com/grafana/grafana-plugin-sdk-go/backend/instancemgmt"
	"github.com/grafana/grafana-plugin-sdk-go/data"

	"github.com/intersystems-community/iris-ai-examples/connectors/grafana-iris-datasource/pkg/plugin/client"
)

// QueryTypeSQL runs a SQL statement against IRIS. This is the default
// when a query's queryType is empty, so existing dashboards built before
// SAM metrics support keep working.
const QueryTypeSQL = "sql"

// QueryTypeSAMMetrics scrapes IRIS's built-in SAM/Prometheus metrics
// endpoint (/api/monitor/metrics) instead of running SQL.
const QueryTypeSAMMetrics = "sam_metrics"

// queryModel is the shape of DataQuery.JSON sent by the frontend's query
// editor.
type queryModel struct {
	QueryText string `json:"queryText"`
}

// Datasource implements the Grafana backend plugin contract
// (backend.QueryDataHandler, backend.CheckHealthHandler,
// instancemgmt.InstanceDisposer) for one configured IRIS connection.
type Datasource struct {
	client client.IRISClient
	nowFn  func() time.Time
}

// Compile-time interface checks.
var (
	_ backend.QueryDataHandler      = (*Datasource)(nil)
	_ backend.CheckHealthHandler    = (*Datasource)(nil)
	_ instancemgmt.InstanceDisposer = (*Datasource)(nil)
)

// NewDatasource is the InstanceFactoryFunc registered with
// datasource.Manage in main.go. It builds the REST IRISClient from the
// data source instance's settings.
func NewDatasource(_ context.Context, settings backend.DataSourceInstanceSettings) (instancemgmt.Instance, error) {
	ps, err := LoadPluginSettings(settings)
	if err != nil {
		return nil, err
	}

	restClient := client.NewRESTClient(client.RESTClientConfig{
		BaseURL:            ps.BaseURL(),
		Namespace:          ps.Namespace,
		Username:           ps.Username,
		Password:           ps.Password,
		InsecureSkipVerify: ps.SkipTLSVerify,
		Timeout:            ps.Timeout,
	})

	return NewDatasourceWithClient(restClient), nil
}

// NewDatasourceWithClient builds a Datasource around an already-built
// IRISClient. Production code reaches this only via NewDatasource; tests
// call it directly with a fake client.
func NewDatasourceWithClient(c client.IRISClient) *Datasource {
	return &Datasource{client: c, nowFn: time.Now}
}

// Dispose implements instancemgmt.InstanceDisposer. The REST client holds
// no resources that need explicit cleanup.
func (d *Datasource) Dispose() {}

// QueryData implements backend.QueryDataHandler.
func (d *Datasource) QueryData(ctx context.Context, req *backend.QueryDataRequest) (*backend.QueryDataResponse, error) {
	response := backend.NewQueryDataResponse()
	for _, q := range req.Queries {
		response.Responses[q.RefID] = d.handleQuery(ctx, q)
	}
	return response, nil
}

func (d *Datasource) handleQuery(ctx context.Context, q backend.DataQuery) backend.DataResponse {
	switch q.QueryType {
	case QueryTypeSAMMetrics:
		return d.handleMetricsQuery(ctx)
	case "", QueryTypeSQL:
		return d.handleSQLQuery(ctx, q)
	default:
		return backend.ErrDataResponse(backend.StatusBadRequest, fmt.Sprintf("iris: unknown queryType %q", q.QueryType))
	}
}

func (d *Datasource) handleSQLQuery(ctx context.Context, q backend.DataQuery) backend.DataResponse {
	var qm queryModel
	if len(q.JSON) > 0 {
		if err := json.Unmarshal(q.JSON, &qm); err != nil {
			return backend.ErrDataResponse(backend.StatusBadRequest, fmt.Sprintf("iris: invalid query JSON: %v", err))
		}
	}
	if qm.QueryText == "" {
		return backend.DataResponse{Frames: data.Frames{}}
	}

	result, err := d.client.Query(ctx, qm.QueryText)
	if err != nil {
		return backend.ErrDataResponse(backend.StatusInternal, fmt.Sprintf("iris: %v", err))
	}

	frame := frameFromQueryResult(q.RefID, result)
	return backend.DataResponse{Frames: data.Frames{frame}}
}

func (d *Datasource) handleMetricsQuery(ctx context.Context) backend.DataResponse {
	samples, err := d.client.Metrics(ctx)
	if err != nil {
		return backend.ErrDataResponse(backend.StatusInternal, fmt.Sprintf("iris: %v", err))
	}
	frame := frameFromMetrics(d.now(), samples)
	return backend.DataResponse{Frames: data.Frames{frame}}
}

func (d *Datasource) now() time.Time {
	if d.nowFn != nil {
		return d.nowFn()
	}
	return time.Now()
}

// CheckHealth implements backend.CheckHealthHandler.
func (d *Datasource) CheckHealth(ctx context.Context, _ *backend.CheckHealthRequest) (*backend.CheckHealthResult, error) {
	if err := d.client.Ping(ctx); err != nil {
		return &backend.CheckHealthResult{
			Status:  backend.HealthStatusError,
			Message: fmt.Sprintf("cannot reach IRIS: %v", err),
		}, nil
	}
	return &backend.CheckHealthResult{
		Status:  backend.HealthStatusOk,
		Message: "IRIS connection OK",
	}, nil
}
