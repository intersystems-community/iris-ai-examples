package plugin

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"github.com/grafana/grafana-plugin-sdk-go/backend"

	"github.com/intersystems-community/iris-ai-examples/connectors/grafana-iris-datasource/pkg/plugin/client"
)

func TestIsReadOnly(t *testing.T) {
	allowed := []string{
		"SELECT 1",
		"  select * from t",
		"SELECT 1;",
		"SELECT 1 ;  \n",
		"-- a comment\nSELECT 1",
		"/* a comment */ SELECT 1",
		"WITH x AS (SELECT 1 AS a) SELECT a FROM x",
		"(SELECT 1) UNION ALL (SELECT 2)",
		"SELECT ';' AS semicolon",
		"SELECT 'DELETE FROM t' AS text FROM t",
		`SELECT "Delete" FROM t`,
		"SELECT 1 -- DELETE FROM t",
		"SELECT /* DROP TABLE t */ 1",
		"SELECT 'it''s; fine'",
	}
	for _, sql := range allowed {
		if ok, why := IsReadOnly(sql); !ok {
			t.Errorf("should be allowed: %q (%s)", sql, why)
		}
	}
	refused := []string{
		"DELETE FROM t",
		"  delete from t",
		"INSERT INTO t VALUES (1)",
		"UPDATE t SET a = 1",
		"DROP TABLE t",
		"TRUNCATE TABLE t",
		"CREATE TABLE t (a INT)",
		"ALTER TABLE t ADD b INT",
		"GRANT SELECT ON t TO u",
		"CALL SomeProc()",
		"SET OPTION SELECTMODE = ODBC",
		"SELECT 1; DELETE FROM t",
		"SELECT 1;DROP TABLE t",
		"SELECT 1 /* x */ ; DROP TABLE t",
		"-- SELECT\nDELETE FROM t",
		"/* SELECT */ DELETE FROM t",
		"",
		"   ",
		"-- only a comment",
		"EXPLAIN DELETE FROM t",
	}
	for _, sql := range refused {
		if ok, _ := IsReadOnly(sql); ok {
			t.Errorf("should be refused: %q", sql)
		}
	}
}

func TestIsReadOnly_TheReasonSaysWhatToDo(t *testing.T) {
	_, why := IsReadOnly("DELETE FROM t")

	if !strings.Contains(why, "Allow data changes") {
		t.Fatalf("the message should name the setting that lifts the guard: %q", why)
	}
}

func TestSQL_ADataChangeIsRefusedByDefaultAndNeverReachesIRIS(t *testing.T) {
	fake := &fakeIRISClient{queryResult: &client.QueryResult{}}
	ds := NewDatasourceWithClient(fake)

	resp, _ := ds.QueryData(context.Background(), sqlRequest(t, map[string]any{"queryText": "DELETE FROM Demo_Metrics"}))

	r := resp.Responses["A"]
	if r.Error == nil || r.Status != backend.StatusBadRequest || r.ErrorSource != backend.ErrorSourceDownstream {
		t.Fatalf("want a downstream 400, got %v / %v / %v", r.Error, r.Status, r.ErrorSource)
	}
	if fake.lastSQL != "" {
		t.Fatalf("the statement must not be sent to IRIS, but %q was", fake.lastSQL)
	}
}

func TestSQL_ADataChangeRunsWhenTheSettingIsOn(t *testing.T) {
	fake := &fakeIRISClient{queryResult: &client.QueryResult{}}
	ds := NewDatasourceWithClient(fake)
	ds.allowWrites = true

	resp, _ := ds.QueryData(context.Background(), sqlRequest(t, map[string]any{"queryText": "DELETE FROM Demo_Metrics"}))

	if r := resp.Responses["A"]; r.Error != nil {
		t.Fatalf("the setting should allow it: %v", r.Error)
	}
	if fake.lastSQL != "DELETE FROM Demo_Metrics" {
		t.Fatalf("sent %q", fake.lastSQL)
	}
}

func TestSQL_TheGuardChecksTheExpandedQueryNotJustTheTypedOne(t *testing.T) {
	fake := &fakeIRISClient{queryResult: &client.QueryResult{}}
	ds := NewDatasourceWithClient(fake)

	resp, _ := ds.QueryData(context.Background(), sqlRequest(t, map[string]any{"queryText": "SELECT 1; DELETE FROM t WHERE $__timeFilter(ts)"}))

	if resp.Responses["A"].Error == nil || fake.lastSQL != "" {
		t.Fatal("a chained statement must be refused")
	}
}

func TestSettings_AllowWritesIsOffUnlessAskedFor(t *testing.T) {
	off := backend.DataSourceInstanceSettings{JSONData: json.RawMessage(`{"host":"h"}`)}
	on := backend.DataSourceInstanceSettings{JSONData: json.RawMessage(`{"host":"h","allowWrites":true}`)}

	a, err := LoadPluginSettings(off)
	if err != nil {
		t.Fatal(err)
	}
	b, err := LoadPluginSettings(on)
	if err != nil {
		t.Fatal(err)
	}

	if a.AllowWrites || !b.AllowWrites {
		t.Fatalf("default off, explicit on: got %v and %v", a.AllowWrites, b.AllowWrites)
	}
}
