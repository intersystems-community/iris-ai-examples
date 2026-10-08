//go:build e2e

package plugin

import (
	"context"
	"encoding/json"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/grafana/grafana-plugin-sdk-go/backend"
	"github.com/grafana/grafana-plugin-sdk-go/data"

	"github.com/intersystems-community/iris-ai-examples/connectors/grafana-iris-datasource/pkg/plugin/client"
)

// Whole-path tests against a real IRIS (PA-02, PA-04). See docker-compose.e2e.yaml and the comment in
// pkg/plugin/client/e2e_test.go for how to run them. They found, in this order: that a DDL TIMESTAMP
// column is returned as a PosixTime number, and that comparing it with a bare string literal silently
// matches nothing. Both are pinned here.

func realDatasource(t *testing.T) (*Datasource, client.IRISClient) {
	t.Helper()
	if os.Getenv("IRIS_URL") == "" || os.Getenv("IRIS_USER") == "" || os.Getenv("IRIS_PASSWORD") == "" {
		t.Fatal("set IRIS_URL, IRIS_USER and IRIS_PASSWORD")
	}
	c := client.NewRESTClient(client.RESTClientConfig{
		BaseURL: os.Getenv("IRIS_URL"), Namespace: "USER",
		Username: os.Getenv("IRIS_USER"), Password: os.Getenv("IRIS_PASSWORD"), Timeout: 30 * time.Second,
	})
	return NewDatasourceWithClient(c), c
}

// seed makes a table with the same two moments in a PosixTime column (tp) and a %TimeStamp column (td),
// for two hosts. The table is dropped when the test ends.
func seed(t *testing.T, c client.IRISClient, table string) {
	t.Helper()
	ctx := context.Background()
	_, _ = c.Query(ctx, "DROP TABLE "+table)
	if _, err := c.Query(ctx, "CREATE TABLE "+table+" (tp TIMESTAMP, td DATETIME, host VARCHAR(20), cpu DOUBLE)"); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _, _ = c.Query(ctx, "DROP TABLE "+table) })
	for _, row := range []struct {
		at   string
		host string
		cpu  string
	}{
		{"2026-10-07 12:00:00", "a", "1.5"}, {"2026-10-07 12:00:00", "b", "2.5"},
		{"2026-10-07 13:00:00", "a", "3.5"}, {"2026-10-07 13:00:00", "b", "4.5"},
		{"2026-10-07 14:30:00", "a", "9.5"},
	} {
		sql := "INSERT INTO " + table + " VALUES ('" + row.at + "','" + row.at + "','" + row.host + "'," + row.cpu + ")"
		if _, err := c.Query(ctx, sql); err != nil {
			t.Fatal(err)
		}
	}
}

func run(t *testing.T, ds *Datasource, qm map[string]any, from, to time.Time) backend.DataResponse {
	t.Helper()
	qj, _ := json.Marshal(qm)
	resp, err := ds.QueryData(context.Background(), &backend.QueryDataRequest{Queries: []backend.DataQuery{
		{RefID: "A", JSON: qj, TimeRange: backend.TimeRange{From: from, To: to}},
	}})
	if err != nil {
		t.Fatal(err)
	}
	return resp.Responses["A"]
}

var (
	t1230 = time.Date(2026, 10, 7, 12, 30, 0, 0, time.UTC)
	t1330 = time.Date(2026, 10, 7, 13, 30, 15, 0, time.UTC)
	t1100 = time.Date(2026, 10, 7, 11, 0, 0, 0, time.UTC)
	t1500 = time.Date(2026, 10, 7, 15, 0, 0, 0, time.UTC)
)

func TestE2E_TimeFilterWorksOnBothKindsOfTimestampColumn(t *testing.T) {
	ds, c := realDatasource(t)
	seed(t, c, "E2E_Metrics")
	for _, col := range []string{"tp", "td"} {
		r := run(t, ds, map[string]any{"queryText": "SELECT host FROM E2E_Metrics WHERE $__timeFilter(" + col + ")"}, t1230, t1330)
		if r.Error != nil {
			t.Fatalf("%s: %v", col, r.Error)
		}
		if got := r.Frames[0].Rows(); got != 2 {
			t.Fatalf("%s: the 13:00 rows of both hosts are in range, got %d rows", col, got)
		}
	}
}

func TestE2E_APosixTimeColumnComesBackAsATime(t *testing.T) {
	ds, c := realDatasource(t)
	seed(t, c, "E2E_Metrics")

	r := run(t, ds, map[string]any{"queryText": "SELECT tp, td FROM E2E_Metrics WHERE host = 'a' ORDER BY tp"}, t1100, t1500)

	if r.Error != nil {
		t.Fatal(r.Error)
	}
	f := r.Frames[0]
	for i := 0; i < 2; i++ {
		if f.Fields[i].Type() != data.FieldTypeNullableTime {
			t.Fatalf("%s is %v, want a time", f.Fields[i].Name, f.Fields[i].Type())
		}
	}
	first, _ := f.Fields[0].ConcreteAt(0)
	second, _ := f.Fields[1].ConcreteAt(0)
	want := time.Date(2026, 10, 7, 12, 0, 0, 0, time.UTC)
	if !first.(time.Time).Equal(want) || !second.(time.Time).Equal(want) {
		t.Fatalf("both columns must read 12:00 UTC, got %v and %v", first, second)
	}
}

func TestE2E_TimeSeriesFormatGivesOneSeriesPerHost(t *testing.T) {
	ds, c := realDatasource(t)
	seed(t, c, "E2E_Metrics")

	r := run(t, ds, map[string]any{
		"queryText": "SELECT tp, host, cpu FROM E2E_Metrics WHERE $__timeFilter(tp) ORDER BY tp",
		"format":    "time_series",
	}, t1100, t1500)

	if r.Error != nil {
		t.Fatal(r.Error)
	}
	f := r.Frames[0]
	var series []string
	for _, fld := range f.Fields[1:] {
		series = append(series, fld.Labels.String())
	}
	if len(series) != 2 || !strings.Contains(strings.Join(series, " "), "host=a") || !strings.Contains(strings.Join(series, " "), "host=b") {
		t.Fatalf("want two series (host a and b), got %v", series)
	}
	if f.Rows() != 3 {
		t.Fatalf("three distinct times (12:00, 13:00, 14:30), got %d", f.Rows())
	}
}

func TestE2E_ASQLErrorIsTheUsersToFixAndCarriesIRISsMessage(t *testing.T) {
	ds, _ := realDatasource(t)

	r := run(t, ds, map[string]any{"queryText": "SELECT nope FROM No_Such_Table"}, t1100, t1500)

	if r.Error == nil || !strings.Contains(r.Error.Error(), "SQLCODE") {
		t.Fatalf("want IRIS's own SQL error, got %v", r.Error)
	}
	if r.Status != backend.StatusBadRequest || r.ErrorSource != backend.ErrorSourceDownstream {
		t.Fatalf("a bad statement is the user's to fix: %v / %v", r.Status, r.ErrorSource)
	}
}

func countRows(t *testing.T, c client.IRISClient, table string) int {
	t.Helper()
	qr, err := c.Query(context.Background(), "SELECT COUNT(*) AS n FROM "+table)
	if err != nil {
		t.Fatal(err)
	}
	switch n := qr.Rows[0][0].(type) {
	case float64:
		return int(n)
	default:
		t.Fatalf("unexpected count type %T", n)
		return -1
	}
}

func TestE2E_TheDefaultDataSourceWillNotChangeDataButTheSettingLiftsTheGuard(t *testing.T) {
	ds, c := realDatasource(t)
	seed(t, c, "E2E_Guard")
	before := countRows(t, c, "E2E_Guard")

	r := run(t, ds, map[string]any{"queryText": "DELETE FROM E2E_Guard"}, t1100, t1500)

	if r.Error == nil || r.Status != backend.StatusBadRequest {
		t.Fatalf("the guard should refuse a DELETE by default: %v / %v", r.Error, r.Status)
	}
	if after := countRows(t, c, "E2E_Guard"); after != before {
		t.Fatalf("the rows changed (%d -> %d) although the statement was refused", before, after)
	}

	ds.allowWrites = true
	r = run(t, ds, map[string]any{"queryText": "DELETE FROM E2E_Guard"}, t1100, t1500)
	if r.Error != nil {
		t.Fatalf("with writes allowed the statement should run: %v", r.Error)
	}
	if after := countRows(t, c, "E2E_Guard"); after != 0 {
		t.Fatalf("writes were allowed, so the table should be empty, got %d rows", after)
	}
}
