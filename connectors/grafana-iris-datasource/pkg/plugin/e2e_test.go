//go:build e2e

package plugin

import (
	"context"
	"encoding/json"
	"net"
	"net/url"
	"os"
	"strconv"
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

func TestE2E_TimeGroupBucketsBothKindsOfTimestampColumn(t *testing.T) {
	ds, c := realDatasource(t)
	seed(t, c, "E2E_Metrics")
	for _, col := range []string{"tp", "td"} {
		r := run(t, ds, map[string]any{
			"queryText": "SELECT $__timeGroup(" + col + ", 1h) AS bucket, AVG(cpu) AS cpu FROM E2E_Metrics " +
				"WHERE $__timeFilter(" + col + ") GROUP BY $__timeGroup(" + col + ", 1h) ORDER BY bucket",
			"format": "time_series",
		}, t1100, t1500)
		if r.Error != nil {
			t.Fatalf("%s: %v", col, r.Error)
		}
		f := r.Frames[0]
		if f.Rows() != 3 {
			t.Fatalf("%s: 12:00, 13:00 and the 14:30 reading in the 14:00 bucket, got %d rows", col, f.Rows())
		}
		if f.Fields[0].Type() != data.FieldTypeNullableTime && f.Fields[0].Type() != data.FieldTypeTime {
			t.Fatalf("%s: the bucket must come back as a time, got %v", col, f.Fields[0].Type())
		}
		got, _ := f.Fields[0].ConcreteAt(2)
		if want := time.Date(2026, 10, 7, 14, 0, 0, 0, time.UTC); !got.(time.Time).Equal(want) {
			t.Fatalf("%s: 14:30 belongs in the 14:00 bucket, got %v", col, got)
		}
		avg, _ := f.Fields[1].ConcreteAt(0)
		if avg.(float64) != 2.0 {
			t.Fatalf("%s: the 12:00 hour averages 1.5 and 2.5, got %v", col, avg)
		}
	}
}

// The same whole-path checks over the native transport: one query must read the same over either.

func nativeDatasource(t *testing.T) (*Datasource, client.IRISClient) {
	t.Helper()
	addr, user, pass := os.Getenv("IRIS_SUPERSERVER"), os.Getenv("IRIS_USER"), os.Getenv("IRIS_PASSWORD")
	if addr == "" || user == "" || pass == "" {
		t.Fatal("set IRIS_SUPERSERVER, IRIS_USER and IRIS_PASSWORD")
	}
	host, portText, err := net.SplitHostPort(addr)
	if err != nil {
		t.Fatal(err)
	}
	port, _ := strconv.Atoi(portText)
	c := client.NewNativeClient(client.NativeClientConfig{Host: host, Port: port, Namespace: "USER", Username: user, Password: pass, Timeout: 30 * time.Second})
	t.Cleanup(func() { _ = c.Close() })
	return NewDatasourceWithClient(c), c
}

func TestNativeE2E_TimeFilterTimeGroupAndPosixTimeMatchTheRESTPath(t *testing.T) {
	ds, c := nativeDatasource(t)
	seed(t, c, "NE2E_Metrics")
	for _, col := range []string{"tp", "td"} {
		r := run(t, ds, map[string]any{
			"queryText": "SELECT $__timeGroup(" + col + ", 1h) AS bucket, AVG(cpu) AS cpu FROM NE2E_Metrics " +
				"WHERE $__timeFilter(" + col + ") GROUP BY $__timeGroup(" + col + ", 1h) ORDER BY bucket",
			"format": "time_series",
		}, t1100, t1500)
		if r.Error != nil {
			t.Fatalf("%s: %v", col, r.Error)
		}
		f := r.Frames[0]
		if f.Rows() != 3 {
			t.Fatalf("%s: want 3 hourly buckets, got %d", col, f.Rows())
		}
		first, _ := f.Fields[0].ConcreteAt(0)
		if want := time.Date(2026, 10, 7, 12, 0, 0, 0, time.UTC); !first.(time.Time).Equal(want) {
			t.Fatalf("%s: first bucket %v, want %v", col, first, want)
		}
		avg, _ := f.Fields[1].ConcreteAt(0)
		if avg.(float64) != 2.0 {
			t.Fatalf("%s: the 12:00 hour averages 1.5 and 2.5, got %v", col, avg)
		}
	}
}

func TestNativeE2E_APosixTimeColumnComesBackAsATime(t *testing.T) {
	ds, c := nativeDatasource(t)
	seed(t, c, "NE2E_Metrics")

	r := run(t, ds, map[string]any{"queryText": "SELECT tp, td FROM NE2E_Metrics WHERE host = 'a' ORDER BY tp"}, t1100, t1500)

	if r.Error != nil {
		t.Fatal(r.Error)
	}
	want := time.Date(2026, 10, 7, 12, 0, 0, 0, time.UTC)
	for i := 0; i < 2; i++ {
		got, _ := r.Frames[0].Fields[i].ConcreteAt(0)
		if !got.(time.Time).Equal(want) {
			t.Fatalf("%s must read 12:00 UTC, got %v", r.Frames[0].Fields[i].Name, got)
		}
	}
}

func TestNativeE2E_ASQLErrorIsTheUsersToFix(t *testing.T) {
	ds, _ := nativeDatasource(t)

	r := run(t, ds, map[string]any{"queryText": "SELECT nope FROM No_Such_Table"}, t1100, t1500)

	if r.Error == nil || !strings.Contains(r.Error.Error(), "SQLCODE") {
		t.Fatalf("want IRIS's own SQL error, got %v", r.Error)
	}
	if r.Status != backend.StatusBadRequest || r.ErrorSource != backend.ErrorSourceDownstream {
		t.Fatalf("%v / %v", r.Status, r.ErrorSource)
	}
}

func TestNativeE2E_TheReadOnlyGuardStillRefusesBeforeIRISIsAsked(t *testing.T) {
	ds, c := nativeDatasource(t)
	seed(t, c, "NE2E_Guard")
	before := countRows(t, c, "NE2E_Guard")

	r := run(t, ds, map[string]any{"queryText": "DELETE FROM NE2E_Guard"}, t1100, t1500)

	if r.Error == nil || r.Status != backend.StatusBadRequest {
		t.Fatalf("the guard should refuse a DELETE by default: %v / %v", r.Error, r.Status)
	}
	if after := countRows(t, c, "NE2E_Guard"); after != before {
		t.Fatalf("the rows changed (%d -> %d)", before, after)
	}
}

// seedEpochMs makes a table shaped like opsreview's IrisEvents.Events: time as integer epoch milliseconds, a
// text column and a tags column, for two hosts.
func seedEpochMs(t *testing.T, c client.IRISClient, table string) {
	t.Helper()
	ctx := context.Background()
	_, _ = c.Query(ctx, "DROP TABLE "+table)
	if _, err := c.Query(ctx, "CREATE TABLE "+table+" (Ts BIGINT, TsEnd BIGINT, host VARCHAR(20), cpu DOUBLE, msg VARCHAR(80), tags VARCHAR(80))"); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _, _ = c.Query(ctx, "DROP TABLE "+table) })
	for _, row := range []string{
		"1791374400000,1791374460000,'a',1.5,'deploy rev 41','deploy,rev-41'",   // 12:00:00
		"1791374400500,1791374460000,'b',2.5,'config change','config'",          // 12:00:00.5
		"1791378000000,1791378900000,'a',3.5,'Episode 7 opened','episode,ep-7'", // 13:00
		"1791383400000,1791383400000,'a',9.5,'out of range','late'",             // 14:30
	} {
		if _, err := c.Query(ctx, "INSERT INTO "+table+" VALUES ("+row+")"); err != nil {
			t.Fatal(err)
		}
	}
}

func TestE2E_EpochMsMacrosAndTimeAxis(t *testing.T) {
	ds, c := realDatasource(t)
	seedEpochMs(t, c, "E2E_EpochMs")

	r := run(t, ds, map[string]any{
		"queryText": "SELECT $__unixEpochMsGroup(Ts, 1h) AS \"time\", AVG(cpu) AS cpu FROM E2E_EpochMs " +
			"WHERE $__unixEpochMsFilter(Ts) GROUP BY $__unixEpochMsGroup(Ts, 1h) ORDER BY \"time\"",
		"format": "time_series",
	}, t1100, t1330)

	if r.Error != nil {
		t.Fatal(r.Error)
	}
	f := r.Frames[0]
	if f.Rows() != 2 {
		t.Fatalf("12:00 and 13:00 are in range and 14:30 is not, got %d rows", f.Rows())
	}
	first, _ := f.Fields[0].ConcreteAt(0)
	if want := time.Date(2026, 10, 7, 12, 0, 0, 0, time.UTC); !first.(time.Time).Equal(want) {
		t.Fatalf("an integer-ms column aliased as time must be the time axis, bucketed to 12:00; got %v", first)
	}
	avg, _ := f.Fields[1].ConcreteAt(0)
	if avg.(float64) != 2.0 {
		t.Fatalf("the 12:00 hour averages 1.5 and 2.5, got %v", avg)
	}
}

// An annotation query is a table query whose columns are named time, timeEnd, text and tags; Grafana maps them.
// TIME is a reserved word in IRIS SQL, so the alias is quoted: AS "time". The others need no quotes.
func TestE2E_AnAnnotationShapedQueryReturnsTimesAndText(t *testing.T) {
	ds, c := realDatasource(t)
	seedEpochMs(t, c, "E2E_Anno")

	r := run(t, ds, map[string]any{
		"queryText": "SELECT Ts AS \"time\", TsEnd AS timeEnd, msg AS text, tags FROM E2E_Anno WHERE $__unixEpochMsFilter(Ts) ORDER BY Ts",
	}, t1100, t1330)

	if r.Error != nil {
		t.Fatal(r.Error)
	}
	f := r.Frames[0]
	if f.Rows() != 3 {
		t.Fatalf("want the three in-range events, got %d", f.Rows())
	}
	names := map[string]data.FieldType{}
	for _, fld := range f.Fields {
		names[fld.Name] = fld.Type()
	}
	if names["time"] != data.FieldTypeNullableTime || names["timeEnd"] != data.FieldTypeNullableTime {
		t.Fatalf("time and timeEnd must be times, got %v", names)
	}
	if names["text"] != data.FieldTypeNullableString || names["tags"] != data.FieldTypeNullableString {
		t.Fatalf("text and tags must be strings, got %v", names)
	}
	end, _ := f.Fields[1].ConcreteAt(2)
	if want := time.Date(2026, 10, 7, 13, 15, 0, 0, time.UTC); !end.(time.Time).Equal(want) {
		t.Fatalf("the Episode band must end at 13:15, got %v", end)
	}
	half, _ := f.Fields[0].ConcreteAt(1)
	if want := time.Date(2026, 10, 7, 12, 0, 0, 500_000_000, time.UTC); !half.(time.Time).Equal(want) {
		t.Fatalf("millisecond precision must survive, got %v", half)
	}
}

// The terminal transport, built from settings the way Grafana builds it, so the SDK's HTTP client is in the path.

func terminalDatasource(t *testing.T, user, password string) *Datasource {
	t.Helper()
	u, err := url.Parse(os.Getenv("IRIS_URL"))
	if err != nil || u.Host == "" {
		t.Fatal("set IRIS_URL")
	}
	port, _ := strconv.Atoi(u.Port())
	js, _ := json.Marshal(map[string]any{"host": u.Hostname(), "webPort": port, "namespace": "USER", "username": user, "transport": "terminal"})
	inst, err := NewDatasource(context.Background(), backend.DataSourceInstanceSettings{JSONData: js, DecryptedSecureJSONData: map[string]string{"password": password}})
	if err != nil {
		t.Fatal(err)
	}
	return inst.(*Datasource)
}

func TestTerminalE2E_TimeFilterAndTimeGroupMatchTheRESTPath(t *testing.T) {
	_, rest := realDatasource(t)
	seed(t, rest, "TE2E_Metrics")
	ds := terminalDatasource(t, os.Getenv("IRIS_USER"), os.Getenv("IRIS_PASSWORD"))
	for _, col := range []string{"tp", "td"} {
		r := run(t, ds, map[string]any{
			"queryText": "SELECT $__timeGroup(" + col + ", 1h) AS bucket, AVG(cpu) AS cpu FROM TE2E_Metrics " +
				"WHERE $__timeFilter(" + col + ") GROUP BY $__timeGroup(" + col + ", 1h) ORDER BY bucket",
			"format": "time_series",
		}, t1100, t1500)
		if r.Error != nil {
			t.Fatalf("%s: %v", col, r.Error)
		}
		f := r.Frames[0]
		if f.Rows() != 3 {
			t.Fatalf("%s: want 3 hourly buckets, got %d", col, f.Rows())
		}
		first, _ := f.Fields[0].ConcreteAt(0)
		if want := time.Date(2026, 10, 7, 12, 0, 0, 0, time.UTC); !first.(time.Time).Equal(want) {
			t.Fatalf("%s: first bucket %v, want %v", col, first, want)
		}
		avg, _ := f.Fields[1].ConcreteAt(0)
		if avg.(float64) != 2.0 {
			t.Fatalf("%s: the 12:00 hour averages 1.5 and 2.5, got %v", col, avg)
		}
	}
}

func TestTerminalE2E_ARefusedReadIsTheUsersToFixAndHealthStillPasses(t *testing.T) {
	_, rest := realDatasource(t)
	seed(t, rest, "TE2E_Private")
	ctx := context.Background()
	_, _ = rest.Query(ctx, "DROP USER te2eviewer")
	for _, sql := range []string{"CREATE USER te2eviewer IDENTIFY BY 'te2e-pw'", "GRANT %Developer TO te2eviewer"} {
		if _, err := rest.Query(ctx, sql); err != nil {
			t.Fatal(err)
		}
	}
	t.Cleanup(func() { _, _ = rest.Query(ctx, "DROP USER te2eviewer") })
	ds := terminalDatasource(t, "te2eviewer", "te2e-pw")

	health, err := ds.CheckHealth(ctx, &backend.CheckHealthRequest{})
	if err != nil || health.Status != backend.HealthStatusOk {
		t.Fatalf("health: %+v %v", health, err)
	}
	r := run(t, ds, map[string]any{"queryText": "SELECT * FROM TE2E_Private"}, t1100, t1500)
	if r.Error == nil || !strings.Contains(r.Error.Error(), "not privileged") {
		t.Fatalf("want IRIS's privilege refusal, got %v", r.Error)
	}
	if r.Status != backend.StatusBadRequest || r.ErrorSource != backend.ErrorSourceDownstream {
		t.Fatalf("%v / %v", r.Status, r.ErrorSource)
	}
}
