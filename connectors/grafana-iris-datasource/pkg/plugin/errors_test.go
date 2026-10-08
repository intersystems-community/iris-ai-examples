package plugin

import (
	"context"
	"errors"
	"fmt"
	"testing"

	"github.com/grafana/grafana-plugin-sdk-go/backend"

	"github.com/intersystems-community/iris-ai-examples/connectors/grafana-iris-datasource/pkg/plugin/client"
)

func TestErrorMapping(t *testing.T) {
	cases := []struct {
		name   string
		err    error
		status backend.Status
		source backend.ErrorSource
	}{
		{"IRIS rejected the SQL", &client.SQLError{Code: 5540, Message: "IDENTIFIER expected"}, backend.StatusBadRequest, backend.ErrorSourceDownstream},
		{"wrong credentials", &client.AuthError{HTTPStatus: 401}, backend.StatusUnauthorized, backend.ErrorSourceDownstream},
		{"forbidden", &client.AuthError{HTTPStatus: 403}, backend.StatusForbidden, backend.ErrorSourceDownstream},
		{"server unreachable", &client.UnreachableError{Err: errors.New("connection refused")}, backend.StatusBadGateway, backend.ErrorSourceDownstream},
		{"result too large", &client.TooLargeError{Limit: 1024}, backend.StatusBadRequest, backend.ErrorSourceDownstream},
		{"wrapped errors are still recognised", fmt.Errorf("outer: %w", &client.SQLError{Message: "x"}), backend.StatusBadRequest, backend.ErrorSourceDownstream},
		{"anything unexpected is ours", errors.New("decoder blew up"), backend.StatusInternal, backend.ErrorSourcePlugin},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			fake := &fakeIRISClient{queryErr: c.err}
			ds := NewDatasourceWithClient(fake)

			resp, _ := ds.QueryData(context.Background(), sqlRequest(t, map[string]any{"queryText": "SELECT 1"}))

			r := resp.Responses["A"]
			if r.Error == nil {
				t.Fatal("want an error")
			}
			if r.Status != c.status {
				t.Errorf("status %v, want %v", r.Status, c.status)
			}
			if r.ErrorSource != c.source {
				t.Errorf("source %q, want %q", r.ErrorSource, c.source)
			}
		})
	}
}

func TestErrorMapping_AMalformedQueryAndAnUnknownTypeAreHandledToo(t *testing.T) {
	ds := NewDatasourceWithClient(&fakeIRISClient{queryResult: &client.QueryResult{}})

	resp, _ := ds.QueryData(context.Background(), sqlRequest(t, map[string]any{"queryText": "SELECT $__timeFilter(a b)"}))

	if r := resp.Responses["A"]; r.ErrorSource != backend.ErrorSourceDownstream || r.Status != backend.StatusBadRequest {
		t.Fatalf("a bad macro is the user's: %v / %v", r.Status, r.ErrorSource)
	}
}

func TestErrorMapping_SAMMetricsFailuresAreMappedTheSameWay(t *testing.T) {
	ds := NewDatasourceWithClient(&fakeIRISClient{metricsErr: &client.UnreachableError{Err: errors.New("no route")}})
	qj := []byte(`{}`)

	resp, _ := ds.QueryData(context.Background(), &backend.QueryDataRequest{Queries: []backend.DataQuery{{RefID: "A", QueryType: QueryTypeSAMMetrics, JSON: qj}}})

	if r := resp.Responses["A"]; r.Status != backend.StatusBadGateway || r.ErrorSource != backend.ErrorSourceDownstream {
		t.Fatalf("%v / %v", r.Status, r.ErrorSource)
	}
}
