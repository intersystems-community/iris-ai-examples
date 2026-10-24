package plugin

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"github.com/grafana/grafana-plugin-sdk-go/backend"
	"github.com/grafana/grafana-plugin-sdk-go/data"

	"github.com/intersystems-community/iris-ai-examples/connectors/grafana-iris-datasource/pkg/plugin/client"
)

func sqlRequest(t *testing.T, qm map[string]any) *backend.QueryDataRequest {
	t.Helper()
	qj, err := json.Marshal(qm)
	if err != nil {
		t.Fatal(err)
	}
	return &backend.QueryDataRequest{Queries: []backend.DataQuery{{RefID: "A", JSON: qj, TimeRange: tr}}}
}

func TestSQL_TimeMacrosAreExpandedBeforeTheQueryReachesIRIS(t *testing.T) {
	fake := &fakeIRISClient{queryResult: &client.QueryResult{}}
	ds := NewDatasourceWithClient(fake)

	_, err := ds.QueryData(context.Background(), sqlRequest(t, map[string]any{"queryText": "SELECT * FROM T WHERE $__timeFilter(ts)"}))

	if err != nil {
		t.Fatal(err)
	}
	want := "SELECT * FROM T WHERE ts >= CAST('2026-10-07 12:00:00' AS TIMESTAMP) AND ts <= CAST('2026-10-07 13:30:15' AS TIMESTAMP)"
	if fake.lastSQL != want {
		t.Fatalf("\n got: %s\nwant: %s", fake.lastSQL, want)
	}
}

func TestSQL_ABadMacroIsAnErrorForThatQueryNotACrash(t *testing.T) {
	ds := NewDatasourceWithClient(&fakeIRISClient{queryResult: &client.QueryResult{}})

	resp, err := ds.QueryData(context.Background(), sqlRequest(t, map[string]any{"queryText": "SELECT $__timeFilter(a b)"}))

	if err != nil {
		t.Fatal(err)
	}
	r := resp.Responses["A"]
	if r.Error == nil || !strings.Contains(r.Error.Error(), "timeFilter") {
		t.Fatalf("want a $__timeFilter error, got %v", r.Error)
	}
	if r.Status != backend.StatusBadRequest {
		t.Fatalf("a malformed query is the user's to fix: status %v", r.Status)
	}
}

func timeSeriesResult() *client.QueryResult {
	return &client.QueryResult{
		Columns: []client.Column{{Name: "host"}, {Name: "ts"}, {Name: "cpu"}},
		Rows: []client.Row{
			{"a", "2026-10-07 12:00:00", 1.5},
			{"b", "2026-10-07 12:00:00", 2.5},
			{"a", "2026-10-07 12:01:00", 3.5},
			{"b", "2026-10-07 12:01:00", 4.5},
		},
	}
}

func TestFormat_TableIsTheDefaultAndKeepsColumnsAsTheyAre(t *testing.T) {
	ds := NewDatasourceWithClient(&fakeIRISClient{queryResult: timeSeriesResult()})

	resp, _ := ds.QueryData(context.Background(), sqlRequest(t, map[string]any{"queryText": "SELECT ..."}))

	f := resp.Responses["A"].Frames[0]
	if len(f.Fields) != 3 || f.Fields[0].Name != "host" {
		t.Fatalf("table format must not reshape: %v", namesOf(f))
	}
}

func TestFormat_TimeSeriesPutsTimeFirstAndSplitsByTheStringColumns(t *testing.T) {
	ds := NewDatasourceWithClient(&fakeIRISClient{queryResult: timeSeriesResult()})

	resp, _ := ds.QueryData(context.Background(), sqlRequest(t, map[string]any{"queryText": "SELECT ...", "format": "time_series"}))

	r := resp.Responses["A"]
	if r.Error != nil {
		t.Fatal(r.Error)
	}
	f := r.Frames[0]
	if f.Fields[0].Type() != data.FieldTypeNullableTime && f.Fields[0].Type() != data.FieldTypeTime {
		t.Fatalf("time must be first, got %v", namesOf(f))
	}
	if f.Rows() != 2 {
		t.Fatalf("two distinct times, got %d rows", f.Rows())
	}
	var series []string
	for _, fld := range f.Fields[1:] {
		series = append(series, fld.Name+fld.Labels.String())
	}
	joined := strings.Join(series, " ")
	if !strings.Contains(joined, "host=a") || !strings.Contains(joined, "host=b") {
		t.Fatalf("one series per host, got %v", series)
	}
}

func TestFormat_TimeSeriesWithoutATimeColumnSaysSo(t *testing.T) {
	res := &client.QueryResult{Columns: []client.Column{{Name: "n"}}, Rows: []client.Row{{1.0}}}
	ds := NewDatasourceWithClient(&fakeIRISClient{queryResult: res})

	resp, _ := ds.QueryData(context.Background(), sqlRequest(t, map[string]any{"queryText": "SELECT n", "format": "time_series"}))

	r := resp.Responses["A"]
	if r.Error == nil || !strings.Contains(r.Error.Error(), "time") {
		t.Fatalf("want an error naming the missing time column, got %v", r.Error)
	}
	if r.Status != backend.StatusBadRequest {
		t.Fatalf("status %v", r.Status)
	}
}

func TestFormat_TimeSeriesWithNoRowsIsAnEmptyResultNotAnError(t *testing.T) {
	// A Tenant with no data in the range is normal. REST sends no columns for an empty result; the terminal
	// sends the names with no values. Neither can show a timestamp column, and neither is the user's mistake.
	for _, res := range []*client.QueryResult{
		{},
		{Columns: []client.Column{{Name: "time"}, {Name: "lines"}}},
	} {
		ds := NewDatasourceWithClient(&fakeIRISClient{queryResult: res})

		resp, _ := ds.QueryData(context.Background(), sqlRequest(t, map[string]any{"queryText": "SELECT x", "format": "time_series"}))

		r := resp.Responses["A"]
		if r.Error != nil {
			t.Fatalf("%d columns: want no error, got %v", len(res.Columns), r.Error)
		}
		if len(r.Frames) != 1 || r.Frames[0].Rows() != 0 {
			t.Fatalf("%d columns: want one empty frame, got %v", len(res.Columns), r.Frames)
		}
	}
}

func TestFormat_AnUnknownFormatIsRejected(t *testing.T) {
	ds := NewDatasourceWithClient(&fakeIRISClient{queryResult: timeSeriesResult()})

	resp, _ := ds.QueryData(context.Background(), sqlRequest(t, map[string]any{"queryText": "SELECT 1", "format": "heatmap"}))

	if resp.Responses["A"].Error == nil {
		t.Fatal("want an error for an unknown format")
	}
}

func namesOf(f *data.Frame) []string {
	var n []string
	for _, fld := range f.Fields {
		n = append(n, fld.Name)
	}
	return n
}
