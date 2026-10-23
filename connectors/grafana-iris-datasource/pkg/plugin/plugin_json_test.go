package plugin

import (
	"encoding/json"
	"os"
	"regexp"
	"testing"
)

// plugin.json is what the catalog and the validator read; these pin the parts that are decisions.
func TestPluginJSON(t *testing.T) {
	raw, err := os.ReadFile("../../src/plugin.json")
	if err != nil {
		t.Fatal(err)
	}
	var p struct {
		ID           string `json:"id"`
		Type         string `json:"type"`
		Backend      bool   `json:"backend"`
		Executable   string `json:"executable"`
		Metrics      bool   `json:"metrics"`
		Alerting     bool   `json:"alerting"`
		Annotations  bool   `json:"annotations"`
		Dependencies struct {
			GrafanaDependency string `json:"grafanaDependency"`
		} `json:"dependencies"`
		Info struct {
			Screenshots []struct {
				Name string `json:"name"`
				Path string `json:"path"`
			} `json:"screenshots"`
		} `json:"info"`
	}
	if err := json.Unmarshal(raw, &p); err != nil {
		t.Fatal(err)
	}

	if !regexp.MustCompile(`^[0-9a-z]+-([0-9a-z]+-)?datasource$`).MatchString(p.ID) {
		t.Errorf("id %q does not fit the catalog's pattern (<org>-<name>-datasource)", p.ID)
	}
	if p.Type != "datasource" || !p.Backend || p.Executable == "" {
		t.Errorf("must be a backend data source with an executable: %+v", p)
	}
	if !p.Alerting {
		t.Error("alerting must be true: the whole query path is in the backend (PA-05)")
	}
	if !p.Annotations {
		t.Error("annotations must be true: a SQL query can be a dashboard annotation source")
	}
	if !p.Metrics {
		t.Error("metrics must be true")
	}
	if len(p.Info.Screenshots) < 3 {
		t.Errorf("the catalog listing wants screenshots; have %d", len(p.Info.Screenshots))
	}
	for _, shot := range p.Info.Screenshots {
		if _, err := os.Stat("../../src/" + shot.Path); err != nil {
			t.Errorf("screenshot %q is declared but missing: %v", shot.Path, err)
		}
	}
	if p.Dependencies.GrafanaDependency != ">=11.1.0" {
		t.Errorf("grafanaDependency %q; the template writes the newest Grafana here, which would not load on 11.1", p.Dependencies.GrafanaDependency)
	}
}
