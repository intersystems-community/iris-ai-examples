package plugin

import (
	"encoding/json"
	"fmt"
	"sort"
	"time"

	"github.com/grafana/grafana-plugin-sdk-go/data"

	"github.com/intersystems-community/iris-ai-examples/connectors/grafana-iris-datasource/pkg/plugin/client"
)

// A handful of layouts IRIS commonly renders SQL DATE/TIME/TIMESTAMP
// columns as over REST/JSON, tried in order.
var timeLayouts = []string{
	"2006-01-02 15:04:05.999999",
	"2006-01-02 15:04:05",
	"2006-01-02T15:04:05.999999Z07:00",
	time.RFC3339,
	"2006-01-02",
}

// frameFromQueryResult converts a SQL QueryResult into a single Grafana
// data.Frame, one field per column, inferring each field's Grafana type
// from the values actually present since the REST/SQL transport does not
// carry IRIS column-type metadata on the plain query call (see
// client/rest_client.go doc comment). Every column is built as a nullable
// (pointer-slice) field so a NULL in any row doesn't force the whole
// column to string.
func frameFromQueryResult(frameName string, qr *client.QueryResult) *data.Frame {
	frame := data.NewFrame(frameName)
	if qr == nil || len(qr.Columns) == 0 {
		return frame
	}

	for colIdx, col := range qr.Columns {
		values := make([]interface{}, len(qr.Rows))
		for rowIdx, row := range qr.Rows {
			if colIdx < len(row) {
				values[rowIdx] = row[colIdx]
			}
		}
		frame.Fields = append(frame.Fields, fieldFromValues(col.Name, values))
	}
	return frame
}

// fieldFromValues inspects every non-nil value in a column and builds the
// most specific nullable Grafana field type all of them agree on, falling
// back to *string (via fmt-free stringification) when the column is
// empty or its values don't agree on a single type.
func fieldFromValues(name string, values []interface{}) *data.Field {
	kind := classifyColumn(values)
	switch kind {
	case colBool:
		out := make([]*bool, len(values))
		for i, v := range values {
			if b, ok := v.(bool); ok {
				out[i] = &b
			}
		}
		return data.NewField(name, nil, out)
	case colFloat:
		out := make([]*float64, len(values))
		for i, v := range values {
			if f, ok := toFloat64(v); ok {
				out[i] = &f
			}
		}
		return data.NewField(name, nil, out)
	case colTime:
		out := make([]*time.Time, len(values))
		for i, v := range values {
			if t, ok := toTime(v); ok {
				out[i] = &t
			}
		}
		return data.NewField(name, nil, out)
	default:
		out := make([]*string, len(values))
		for i, v := range values {
			if v == nil {
				continue
			}
			s := toDisplayString(v)
			out[i] = &s
		}
		return data.NewField(name, nil, out)
	}
}

type columnKind int

const (
	colString columnKind = iota
	colBool
	colFloat
	colTime
)

// classifyColumn decides one Grafana field type for a column by checking
// whether every non-nil value fits progressively looser types, in order
// of specificity: bool, then numeric, then time, else string.
func classifyColumn(values []interface{}) columnKind {
	sawAny := false
	allBool, allFloat, allTime := true, true, true
	for _, v := range values {
		if v == nil {
			continue
		}
		sawAny = true
		if _, ok := v.(bool); !ok {
			allBool = false
		}
		if _, ok := toFloat64(v); !ok {
			allFloat = false
		}
		if _, ok := toTime(v); !ok {
			allTime = false
		}
	}
	if !sawAny {
		return colString
	}
	switch {
	case allBool:
		return colBool
	case allFloat:
		return colFloat
	case allTime:
		return colTime
	default:
		return colString
	}
}

func toFloat64(v interface{}) (float64, bool) {
	switch n := v.(type) {
	case float64:
		return n, true
	case float32:
		return float64(n), true
	case int:
		return float64(n), true
	case int64:
		return float64(n), true
	}
	return 0, false
}

func toTime(v interface{}) (time.Time, bool) {
	s, ok := v.(string)
	if !ok {
		return time.Time{}, false
	}
	for _, layout := range timeLayouts {
		if t, err := time.Parse(layout, s); err == nil {
			return t, true
		}
	}
	return time.Time{}, false
}

func toDisplayString(v interface{}) string {
	switch s := v.(type) {
	case string:
		return s
	case float64, float32, int, int64, bool:
		return fmt.Sprintf("%v", s)
	default:
		// Nested object/array columns: fall back to their JSON
		// representation rather than dropping the value.
		b, err := json.Marshal(v)
		if err != nil {
			return fmt.Sprintf("%v", v)
		}
		return string(b)
	}
}

// frameFromMetrics converts SAM/Prometheus samples scraped from IRIS into
// a single wide-format table frame: one row per sample, a "time" column
// stamped with the scrape time, a "metric" column, one nullable string
// column per distinct label key seen across all samples, and a "value"
// column. Every query returns the current snapshot IRIS reports at scrape
// time — this transport has no access to IRIS's own metric history, so it
// cannot backfill a time range. See README.md/STATUS.md for that
// limitation and how a Grafana panel should be configured around it.
func frameFromMetrics(scrapedAt time.Time, samples []client.MetricSample) *data.Frame {
	frame := data.NewFrame("sam_metrics")

	labelKeys := distinctLabelKeys(samples)

	times := make([]time.Time, len(samples))
	metrics := make([]string, len(samples))
	values := make([]float64, len(samples))
	for i, s := range samples {
		times[i] = scrapedAt
		metrics[i] = s.Name
		values[i] = s.Value
	}

	frame.Fields = append(frame.Fields, data.NewField("time", nil, times))
	frame.Fields = append(frame.Fields, data.NewField("metric", nil, metrics))
	for _, key := range labelKeys {
		col := make([]*string, len(samples))
		for i, s := range samples {
			if v, ok := s.Labels[key]; ok {
				vv := v
				col[i] = &vv
			}
		}
		frame.Fields = append(frame.Fields, data.NewField(key, nil, col))
	}
	frame.Fields = append(frame.Fields, data.NewField("value", nil, values))

	return frame
}

func distinctLabelKeys(samples []client.MetricSample) []string {
	seen := map[string]bool{}
	for _, s := range samples {
		for k := range s.Labels {
			seen[k] = true
		}
	}
	keys := make([]string, 0, len(seen))
	for k := range seen {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}
