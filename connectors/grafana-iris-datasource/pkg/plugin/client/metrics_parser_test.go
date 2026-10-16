package client

import "testing"

func TestParseOpenMetrics_LabelsAndBareMetrics(t *testing.T) {
	input := `# HELP iris_up whether IRIS is up
# TYPE iris_up gauge
iris_up{instance="IRIS",ns="USER"} 1
iris_global_refs_total 42
# a comment with no leading TYPE/HELP marker

iris_wd_load{node="a,b",instance="IRIS"} 3.5
`
	samples, err := parseOpenMetrics([]byte(input))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(samples) != 3 {
		t.Fatalf("expected 3 samples, got %d: %+v", len(samples), samples)
	}

	if samples[0].Name != "iris_up" || samples[0].Value != 1 {
		t.Errorf("sample 0 = %+v", samples[0])
	}
	if samples[0].Labels["instance"] != "IRIS" || samples[0].Labels["ns"] != "USER" {
		t.Errorf("sample 0 labels = %+v", samples[0].Labels)
	}

	if samples[1].Name != "iris_global_refs_total" || samples[1].Value != 42 || len(samples[1].Labels) != 0 {
		t.Errorf("sample 1 = %+v", samples[1])
	}

	if samples[2].Labels["node"] != "a,b" {
		t.Errorf("expected comma inside quoted label value to survive, got %+v", samples[2].Labels)
	}
}

func TestParseOpenMetrics_SkipsMalformedLines(t *testing.T) {
	input := "not_a_metric_line_without_value\n" +
		"broken{unterminated_label\n" +
		"valid_metric 7\n"
	samples, err := parseOpenMetrics([]byte(input))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(samples) != 1 || samples[0].Name != "valid_metric" || samples[0].Value != 7 {
		t.Fatalf("expected only valid_metric to parse, got %+v", samples)
	}
}

func TestParseOpenMetrics_Empty(t *testing.T) {
	samples, err := parseOpenMetrics([]byte(""))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(samples) != 0 {
		t.Fatalf("expected no samples, got %+v", samples)
	}
}
