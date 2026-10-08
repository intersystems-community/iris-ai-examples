package plugin

import (
	"testing"
	"time"

	"github.com/grafana/grafana-plugin-sdk-go/data"
)

// Measured on a real IRIS: a TIMESTAMP column made by DDL is a PosixTime, and the REST/SQL path
// returns its internal value, a decimal string equal to unix microseconds plus 2^60. These values
// are real: 2026-10-07 12:00:00 and 13:00:00 UTC.
const (
	posixNoon = "1154712879006846976"
	posix1pm  = "1154712882606846976"
)

func TestToTime_DecodesAPosixTimeNumber(t *testing.T) {
	got, ok := toTime(posixNoon)

	if !ok {
		t.Fatal("a PosixTime value must be read as a time")
	}
	want := time.Date(2026, 10, 7, 12, 0, 0, 0, time.UTC)
	if !got.Equal(want) {
		t.Fatalf("got %s want %s", got, want)
	}
}

func TestToTime_OrdinaryNumbersAndTextAreNotTimes(t *testing.T) {
	for _, s := range []string{"12345", "0", "-5", "1154712879", "99999999999999999999", "abc", "", "1154712879006846976x"} {
		if _, ok := toTime(s); ok {
			t.Fatalf("%q must not be read as a time", s)
		}
	}
}

func TestClassifyColumn_APosixColumnIsATimeColumn(t *testing.T) {
	if got := classifyColumn([]interface{}{posixNoon, posix1pm}); got != colTime {
		t.Fatalf("got %v", got)
	}
}

func TestClassifyColumn_AColumnOfSmallIntegerStringsStaysAString(t *testing.T) {
	if got := classifyColumn([]interface{}{"101", "202"}); got != colString {
		t.Fatalf("got %v", got)
	}
}

func TestFieldFromValues_AnEmptyStringInATimeColumnIsNull(t *testing.T) {
	// IRIS sends NULL as "" on this path, so "" cannot be allowed to turn a time column into text.
	f := fieldFromValues("ts", []interface{}{posixNoon, "", "2026-10-07 13:00:00"})

	if f.Type() != data.FieldTypeNullableTime {
		t.Fatalf("type %v", f.Type())
	}
	if _, isNull := f.ConcreteAt(1); isNull {
		// ConcreteAt reports ok=false for nil
	}
	if v, ok := f.ConcreteAt(1); ok {
		t.Fatalf("row 1 must be null, got %v", v)
	}
	if v, ok := f.ConcreteAt(0); !ok || !v.(time.Time).Equal(time.Date(2026, 10, 7, 12, 0, 0, 0, time.UTC)) {
		t.Fatalf("row 0: %v %v", v, ok)
	}
}

func TestFieldFromValues_AllEmptyStringsStayAStringColumn(t *testing.T) {
	f := fieldFromValues("s", []interface{}{"", ""})

	if f.Type() != data.FieldTypeNullableString {
		t.Fatalf("type %v", f.Type())
	}
}
