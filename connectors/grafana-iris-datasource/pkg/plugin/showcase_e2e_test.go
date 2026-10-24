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
)

// The showcase dashboard (e2e/grafana/dashboards/iris-showcase.json) over the synthetic dataset that
// e2e/seed-showcase.sh loads. Every panel and annotation query in the file runs for real, for each Tenant, so a
// dashboard edit that breaks a query fails here rather than on screen.

type showcaseQuery struct {
	Name      string `json:"name"`
	Title     string `json:"title"`
	QueryText string `json:"queryText"`
	Format    string `json:"format"`
}

func showcaseQueries(t *testing.T) (panels, annotations []showcaseQuery) {
	t.Helper()
	raw, err := os.ReadFile("../../e2e/grafana/dashboards/iris-showcase.json")
	if err != nil {
		t.Fatal(err)
	}
	var d struct {
		Panels []struct {
			Title   string          `json:"title"`
			Targets []showcaseQuery `json:"targets"`
		} `json:"panels"`
		Annotations struct {
			List []struct {
				Name   string        `json:"name"`
				Target showcaseQuery `json:"target"`
			} `json:"list"`
		} `json:"annotations"`
	}
	if err := json.Unmarshal(raw, &d); err != nil {
		t.Fatal(err)
	}
	for _, p := range d.Panels {
		for _, q := range p.Targets {
			q.Title = p.Title
			panels = append(panels, q)
		}
	}
	for _, a := range d.Annotations.List {
		if a.Target.QueryText != "" {
			q := a.Target
			q.Title = a.Name
			annotations = append(annotations, q)
		}
	}
	return panels, annotations
}

// The Tenants e2e/seed-showcase.sh loads.
var showcaseTenants = []string{"acme", "globex"}

func seededShowcaseDatasource(t *testing.T) *Datasource {
	t.Helper()
	ds, c := realDatasource(t)
	res, err := c.Query(context.Background(), "SELECT COUNT(*) AS n FROM Demo.Events")
	if err != nil || len(res.Rows) == 0 || res.Rows[0][0].(float64) == 0 {
		t.Fatalf("run ./e2e/seed-showcase.sh first (%v)", err)
	}
	return ds
}

func runShowcase(t *testing.T, ds *Datasource, q showcaseQuery, tenant string) backend.DataResponse {
	t.Helper()
	qj, _ := json.Marshal(map[string]any{"queryText": strings.ReplaceAll(q.QueryText, "$tenant", tenant), "format": q.Format})
	now := time.Now()
	resp, err := ds.QueryData(context.Background(), &backend.QueryDataRequest{Queries: []backend.DataQuery{{
		RefID: "A", JSON: qj, Interval: 10 * time.Minute,
		TimeRange: backend.TimeRange{From: now.Add(-49 * time.Hour), To: now},
	}}})
	if err != nil {
		t.Fatal(err)
	}
	return resp.Responses["A"]
}

func TestShowcaseE2E_EveryPanelQueryReturnsRowsForEachTenant(t *testing.T) {
	ds := seededShowcaseDatasource(t)
	panels, _ := showcaseQueries(t)
	if len(panels) < 3 {
		t.Fatalf("the dashboard has %d panel queries, want at least 3", len(panels))
	}
	for _, tenant := range showcaseTenants {
		for _, q := range panels {
			r := runShowcase(t, ds, q, tenant)
			if r.Error != nil {
				t.Fatalf("%s / %s: %v", tenant, q.Title, r.Error)
			}
			if len(r.Frames) == 0 || r.Frames[0].Rows() == 0 {
				t.Fatalf("%s / %s: no rows", tenant, q.Title)
			}
		}
	}
}

func TestShowcaseE2E_AnnotationsHaveTimesTextAndTags(t *testing.T) {
	ds := seededShowcaseDatasource(t)
	_, annotations := showcaseQueries(t)
	if len(annotations) != 2 {
		t.Fatalf("want the deploy and Episode annotations, got %d", len(annotations))
	}
	for _, tenant := range showcaseTenants {
		for _, q := range annotations {
			r := runShowcase(t, ds, q, tenant)
			if r.Error != nil {
				t.Fatalf("%s / %s: %v", tenant, q.Title, r.Error)
			}
			f := r.Frames[0]
			if f.Rows() == 0 {
				t.Fatalf("%s / %s: no rows", tenant, q.Title)
			}
			fields := map[string]bool{}
			for _, fld := range f.Fields {
				fields[fld.Name] = true
			}
			for _, want := range []string{"time", "text", "tags"} {
				if !fields[want] {
					t.Fatalf("%s / %s: no %q field in %v", tenant, q.Title, want, fields)
				}
			}
			tm, ok := f.Fields[0].ConcreteAt(0)
			if !ok {
				t.Fatalf("%s / %s: the first time is empty", tenant, q.Title)
			}
			if _, isTime := tm.(time.Time); !isTime {
				t.Fatalf("%s / %s: time is %T, not a time", tenant, q.Title, tm)
			}
		}
	}
}
