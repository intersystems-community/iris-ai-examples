package plugin

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	"github.com/grafana/grafana-plugin-sdk-go/backend"

	"github.com/intersystems-community/iris-ai-examples/connectors/grafana-iris-datasource/pkg/plugin/client"
)

// fakeIRISClient is a hand-written test double for client.IRISClient —
// there is no running IRIS in this environment, so every Datasource test
// exercises this fake rather than a real connection.
type fakeIRISClient struct {
	queryResult   *client.QueryResult
	queryErr      error
	metricsResult []client.MetricSample
	metricsErr    error
	pingErr       error

	lastSQL string
}

func (f *fakeIRISClient) Query(_ context.Context, sql string) (*client.QueryResult, error) {
	f.lastSQL = sql
	if f.queryErr != nil {
		return nil, f.queryErr
	}
	return f.queryResult, nil
}

func (f *fakeIRISClient) Metrics(_ context.Context) ([]client.MetricSample, error) {
	if f.metricsErr != nil {
		return nil, f.metricsErr
	}
	return f.metricsResult, nil
}

func (f *fakeIRISClient) Ping(_ context.Context) error {
	return f.pingErr
}

func TestDatasource_QueryData_SQL(t *testing.T) {
	fake := &fakeIRISClient{
		queryResult: &client.QueryResult{
			Columns: []client.Column{{Name: "N"}},
			Rows:    []client.Row{{float64(1)}, {float64(2)}},
		},
	}
	ds := NewDatasourceWithClient(fake)

	qj, _ := json.Marshal(queryModel{QueryText: "SELECT N FROM T"})
	req := &backend.QueryDataRequest{
		Queries: []backend.DataQuery{
			{RefID: "A", JSON: qj},
		},
	}
	resp, err := ds.QueryData(context.Background(), req)
	if err != nil {
		t.Fatalf("QueryData error: %v", err)
	}
	r, ok := resp.Responses["A"]
	if !ok {
		t.Fatal("missing response for RefID A")
	}
	if r.Error != nil {
		t.Fatalf("unexpected DataResponse error: %v", r.Error)
	}
	if len(r.Frames) != 1 || r.Frames[0].Fields[0].Len() != 2 {
		t.Fatalf("unexpected frames: %+v", r.Frames)
	}
	if fake.lastSQL != "SELECT N FROM T" {
		t.Errorf("client received SQL %q", fake.lastSQL)
	}
}

func TestDatasource_QueryData_SQLError(t *testing.T) {
	fake := &fakeIRISClient{queryErr: errors.New("boom")}
	ds := NewDatasourceWithClient(fake)

	qj, _ := json.Marshal(queryModel{QueryText: "SELECT 1"})
	req := &backend.QueryDataRequest{Queries: []backend.DataQuery{{RefID: "A", JSON: qj}}}
	resp, err := ds.QueryData(context.Background(), req)
	if err != nil {
		t.Fatalf("QueryData transport error: %v", err)
	}
	r := resp.Responses["A"]
	if r.Error == nil {
		t.Fatal("expected a per-query error, got nil")
	}
}

func TestDatasource_QueryData_EmptyQueryText(t *testing.T) {
	fake := &fakeIRISClient{}
	ds := NewDatasourceWithClient(fake)

	qj, _ := json.Marshal(queryModel{QueryText: ""})
	req := &backend.QueryDataRequest{Queries: []backend.DataQuery{{RefID: "A", JSON: qj}}}
	resp, err := ds.QueryData(context.Background(), req)
	if err != nil {
		t.Fatalf("QueryData error: %v", err)
	}
	r := resp.Responses["A"]
	if r.Error != nil {
		t.Fatalf("empty query text should not error, got %v", r.Error)
	}
	if len(r.Frames) != 0 {
		t.Fatalf("expected no frames for empty query text, got %d", len(r.Frames))
	}
	if fake.lastSQL != "" {
		t.Errorf("client should never have been called, got SQL %q", fake.lastSQL)
	}
}

func TestDatasource_QueryData_SAMMetrics(t *testing.T) {
	fake := &fakeIRISClient{
		metricsResult: []client.MetricSample{
			{Name: "iris_up", Value: 1},
		},
	}
	ds := NewDatasourceWithClient(fake)
	ds.nowFn = func() time.Time { return time.Date(2026, 9, 16, 0, 0, 0, 0, time.UTC) }

	req := &backend.QueryDataRequest{
		Queries: []backend.DataQuery{
			{RefID: "A", QueryType: QueryTypeSAMMetrics},
		},
	}
	resp, err := ds.QueryData(context.Background(), req)
	if err != nil {
		t.Fatalf("QueryData error: %v", err)
	}
	r := resp.Responses["A"]
	if r.Error != nil {
		t.Fatalf("unexpected error: %v", r.Error)
	}
	if len(r.Frames) != 1 {
		t.Fatalf("expected 1 frame, got %d", len(r.Frames))
	}
}

func TestDatasource_QueryData_UnknownQueryType(t *testing.T) {
	ds := NewDatasourceWithClient(&fakeIRISClient{})
	req := &backend.QueryDataRequest{
		Queries: []backend.DataQuery{{RefID: "A", QueryType: "nonsense"}},
	}
	resp, err := ds.QueryData(context.Background(), req)
	if err != nil {
		t.Fatalf("QueryData error: %v", err)
	}
	if resp.Responses["A"].Error == nil {
		t.Fatal("expected an error for an unknown query type")
	}
}

func TestDatasource_CheckHealth_OK(t *testing.T) {
	ds := NewDatasourceWithClient(&fakeIRISClient{})
	res, err := ds.CheckHealth(context.Background(), &backend.CheckHealthRequest{})
	if err != nil {
		t.Fatalf("CheckHealth error: %v", err)
	}
	if res.Status != backend.HealthStatusOk {
		t.Fatalf("expected HealthStatusOk, got %v: %s", res.Status, res.Message)
	}
}

func TestDatasource_CheckHealth_Failure(t *testing.T) {
	ds := NewDatasourceWithClient(&fakeIRISClient{pingErr: errors.New("connection refused")})
	res, err := ds.CheckHealth(context.Background(), &backend.CheckHealthRequest{})
	if err != nil {
		t.Fatalf("CheckHealth error: %v", err)
	}
	if res.Status != backend.HealthStatusError {
		t.Fatalf("expected HealthStatusError, got %v", res.Status)
	}
}
