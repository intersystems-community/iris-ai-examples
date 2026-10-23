package plugin

import (
	"testing"
	"time"

	"github.com/grafana/grafana-plugin-sdk-go/data"

	"github.com/intersystems-community/iris-ai-examples/connectors/grafana-iris-datasource/pkg/plugin/client"
)

func fieldByName(t *testing.T, frame *data.Frame, name string) *data.Field {
	t.Helper()
	for _, f := range frame.Fields {
		if f.Name == name {
			return f
		}
	}
	t.Fatalf("frame has no field %q; fields: %v", name, fieldNames(frame))
	return nil
}

func fieldNames(frame *data.Frame) []string {
	names := make([]string, len(frame.Fields))
	for i, f := range frame.Fields {
		names[i] = f.Name
	}
	return names
}

func TestFrameFromQueryResult_TypeInference(t *testing.T) {
	qr := &client.QueryResult{
		Columns: []client.Column{{Name: "ID"}, {Name: "Name"}, {Name: "Active"}, {Name: "Score"}, {Name: "CreatedAt"}},
		Rows: []client.Row{
			{float64(1), "Maria Gonzalez", true, float64(3.5), "2026-01-15 10:30:00"},
			{float64(2), "John Smith", false, float64(-1), "2026-02-01 08:00:00"},
			{nil, nil, nil, nil, nil}, // a fully-NULL row must not break typing
		},
	}
	frame := frameFromQueryResult("A", qr)
	if len(frame.Fields) != 5 {
		t.Fatalf("expected 5 fields, got %d", len(frame.Fields))
	}

	idField := fieldByName(t, frame, "ID")
	if idField.Type() != data.FieldTypeNullableFloat64 {
		t.Errorf("ID field type = %v, want nullable float64", idField.Type())
	}

	activeField := fieldByName(t, frame, "Active")
	if activeField.Type() != data.FieldTypeNullableBool {
		t.Errorf("Active field type = %v, want nullable bool", activeField.Type())
	}

	nameField := fieldByName(t, frame, "Name")
	if nameField.Type() != data.FieldTypeNullableString {
		t.Errorf("Name field type = %v, want nullable string", nameField.Type())
	}

	tsField := fieldByName(t, frame, "CreatedAt")
	if tsField.Type() != data.FieldTypeNullableTime {
		t.Errorf("CreatedAt field type = %v, want nullable time", tsField.Type())
	}
	got, ok := tsField.At(0).(*time.Time)
	if !ok || got == nil {
		t.Fatalf("CreatedAt[0] = %v (%T)", tsField.At(0), tsField.At(0))
	}
	if got.Year() != 2026 || got.Month() != time.January || got.Day() != 15 {
		t.Errorf("CreatedAt[0] parsed as %v", got)
	}

	// The all-NULL row.
	if v := idField.At(2); v != (*float64)(nil) {
		t.Errorf("expected nil for NULL cell, got %v", v)
	}
}

func TestFrameFromQueryResult_MixedTypesFallBackToString(t *testing.T) {
	qr := &client.QueryResult{
		Columns: []client.Column{{Name: "Mixed"}},
		Rows: []client.Row{
			{float64(1)},
			{"not a number"},
		},
	}
	frame := frameFromQueryResult("A", qr)
	f := fieldByName(t, frame, "Mixed")
	if f.Type() != data.FieldTypeNullableString {
		t.Errorf("Mixed field type = %v, want nullable string fallback", f.Type())
	}
}

func TestFrameFromQueryResult_Empty(t *testing.T) {
	frame := frameFromQueryResult("A", &client.QueryResult{})
	if len(frame.Fields) != 0 {
		t.Errorf("expected no fields for empty result, got %d", len(frame.Fields))
	}
	frame = frameFromQueryResult("A", nil)
	if len(frame.Fields) != 0 {
		t.Errorf("expected no fields for nil result, got %d", len(frame.Fields))
	}
}

func TestFrameFromMetrics(t *testing.T) {
	now := time.Date(2026, 9, 16, 12, 0, 0, 0, time.UTC)
	samples := []client.MetricSample{
		{Name: "iris_up", Labels: map[string]string{"instance": "IRIS"}, Value: 1},
		{Name: "iris_global_refs_total", Labels: nil, Value: 42},
	}
	frame := frameFromMetrics(now, samples)

	metricField := fieldByName(t, frame, "metric")
	if metricField.Len() != 2 {
		t.Fatalf("expected 2 rows, got %d", metricField.Len())
	}
	if got := metricField.At(0); got != "iris_up" {
		t.Errorf("metric[0] = %v", got)
	}

	instField := fieldByName(t, frame, "instance")
	v0, ok := instField.At(0).(*string)
	if !ok || v0 == nil || *v0 != "IRIS" {
		t.Errorf("instance[0] = %v", instField.At(0))
	}
	v1, ok := instField.At(1).(*string)
	if !ok || v1 != nil {
		t.Errorf("instance[1] should be nil (label absent), got %v", instField.At(1))
	}

	valueField := fieldByName(t, frame, "value")
	if valueField.At(1) != float64(42) {
		t.Errorf("value[1] = %v", valueField.At(1))
	}
}

// A numeric column named time or timeEnd is read as a Unix epoch, the convention Grafana's SQL data sources
// use, so an integer-ms column can be the time axis or an annotation's span with only an alias. The unit is
// decided by magnitude.
func TestFrameFromQueryResult_NumericTimeColumnIsAnEpoch(t *testing.T) {
	want := time.Date(2026, 10, 7, 12, 0, 0, 0, time.UTC)
	for _, c := range []struct {
		unit  string
		value float64
	}{
		{"seconds", 1791374400},
		{"milliseconds", 1791374400000},
		{"microseconds", 1791374400000000},
		{"nanoseconds", 1791374400000000000},
	} {
		for _, name := range []string{"time", "Time", "timeEnd", "TIMEEND"} {
			qr := &client.QueryResult{Columns: []client.Column{{Name: name}}, Rows: []client.Row{{c.value}, {nil}}}

			f := frameFromQueryResult("A", qr)

			fld := f.Fields[0]
			if fld.Type() != data.FieldTypeNullableTime {
				t.Fatalf("%s in %s: want a time field, got %v", name, c.unit, fld.Type())
			}
			got, _ := fld.ConcreteAt(0)
			if !got.(time.Time).Equal(want) {
				t.Fatalf("%s in %s: got %v, want %v", name, c.unit, got, want)
			}
			if _, ok := fld.ConcreteAt(1); ok {
				t.Fatalf("%s: a NULL must stay NULL", name)
			}
		}
	}
}

func TestFrameFromQueryResult_OtherNumericColumnsStayNumbers(t *testing.T) {
	qr := &client.QueryResult{Columns: []client.Column{{Name: "Ts"}, {Name: "timeout"}}, Rows: []client.Row{{float64(1791374400000), float64(30)}}}

	f := frameFromQueryResult("A", qr)

	for _, fld := range f.Fields {
		if fld.Type() != data.FieldTypeNullableFloat64 {
			t.Fatalf("%s must stay a number (only time and timeEnd are epochs), got %v", fld.Name, fld.Type())
		}
	}
}
