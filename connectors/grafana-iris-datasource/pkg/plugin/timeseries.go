package plugin

import (
	"fmt"

	"github.com/grafana/grafana-plugin-sdk-go/data"
)

// Query result formats.
const (
	// FormatTable returns the result as it came back; the default.
	FormatTable = "table"
	// FormatTimeSeries makes the result plottable: the first timestamp column becomes the time axis
	// and the string columns become labels, one series per distinct combination.
	FormatTimeSeries = "time_series"
)

// asTimeSeries reshapes a SQL result frame for graphing. It needs a timestamp column; rows should
// be ordered by it (ORDER BY the time column), which is what Grafana's time series wants.
func asTimeSeries(f *data.Frame) (*data.Frame, error) {
	timeIdx := -1
	hasLabels := false
	for i, fld := range f.Fields {
		switch {
		case timeIdx < 0 && (fld.Type() == data.FieldTypeTime || fld.Type() == data.FieldTypeNullableTime):
			timeIdx = i
		case fld.Type() == data.FieldTypeString || fld.Type() == data.FieldTypeNullableString:
			hasLabels = true
		}
	}
	if timeIdx < 0 {
		return nil, fmt.Errorf("the time series format needs a timestamp column, and none of the columns [%s] looks like one", joinNames(f))
	}

	// Time first, the rest in their original order.
	ordered := make([]*data.Field, 0, len(f.Fields))
	ordered = append(ordered, f.Fields[timeIdx])
	for i, fld := range f.Fields {
		if i != timeIdx {
			ordered = append(ordered, fld)
		}
	}
	out := data.NewFrame(f.Name, ordered...)

	if !hasLabels {
		out.SetMeta(&data.FrameMeta{Type: data.FrameTypeTimeSeriesWide})
		return out, nil
	}
	out.SetMeta(&data.FrameMeta{Type: data.FrameTypeTimeSeriesLong})
	wide, err := data.LongToWide(out, nil)
	if err != nil {
		return nil, fmt.Errorf("could not split the result into series: %w", err)
	}
	return wide, nil
}

func joinNames(f *data.Frame) string {
	s := ""
	for i, fld := range f.Fields {
		if i > 0 {
			s += ", "
		}
		s += fld.Name
	}
	return s
}
