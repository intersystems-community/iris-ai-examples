package plugin

import (
	"strings"
	"testing"
	"time"

	"github.com/grafana/grafana-plugin-sdk-go/backend"
)

var tr = backend.TimeRange{
	From: time.Date(2026, 10, 7, 12, 0, 0, 0, time.UTC),
	To:   time.Date(2026, 10, 7, 13, 30, 15, 0, time.UTC),
}

func TestExpandMacros(t *testing.T) {
	cases := []struct{ name, in, want string }{
		{"from", "SELECT $__timeFrom()", "SELECT CAST('2026-10-07 12:00:00' AS TIMESTAMP)"},
		{"to", "SELECT $__timeTo()", "SELECT CAST('2026-10-07 13:30:15' AS TIMESTAMP)"},
		{"filter", "WHERE $__timeFilter(ts)", "WHERE ts >= CAST('2026-10-07 12:00:00' AS TIMESTAMP) AND ts <= CAST('2026-10-07 13:30:15' AS TIMESTAMP)"},
		{"filter with spaces", "WHERE $__timeFilter( ts )", "WHERE ts >= CAST('2026-10-07 12:00:00' AS TIMESTAMP) AND ts <= CAST('2026-10-07 13:30:15' AS TIMESTAMP)"},
		{"qualified column", "$__timeFilter(t.CreatedAt)", "t.CreatedAt >= CAST('2026-10-07 12:00:00' AS TIMESTAMP) AND t.CreatedAt <= CAST('2026-10-07 13:30:15' AS TIMESTAMP)"},
		{"quoted column", `$__timeFilter("Event Time")`, `"Event Time" >= CAST('2026-10-07 12:00:00' AS TIMESTAMP) AND "Event Time" <= CAST('2026-10-07 13:30:15' AS TIMESTAMP)`},
		{"two filters", "a $__timeFilter(x) b $__timeFilter(y)", "a x >= CAST('2026-10-07 12:00:00' AS TIMESTAMP) AND x <= CAST('2026-10-07 13:30:15' AS TIMESTAMP) b y >= CAST('2026-10-07 12:00:00' AS TIMESTAMP) AND y <= CAST('2026-10-07 13:30:15' AS TIMESTAMP)"},
		{"no macros", "SELECT 1", "SELECT 1"},
		{"grafana built-in variable left alone", "SELECT $__interval", "SELECT $__interval"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got, err := ExpandMacros(c.in, tr)
			if err != nil {
				t.Fatal(err)
			}
			if got != c.want {
				t.Fatalf("\n got: %s\nwant: %s", got, c.want)
			}
		})
	}
}

func TestExpandMacros_TimesAreUTCWhateverZoneTheRangeIsIn(t *testing.T) {
	est := time.FixedZone("EST", -5*3600)
	r := backend.TimeRange{From: time.Date(2026, 10, 7, 7, 0, 0, 0, est), To: time.Date(2026, 10, 7, 8, 0, 0, 0, est)}

	got, err := ExpandMacros("$__timeFrom() $__timeTo()", r)

	if err != nil {
		t.Fatal(err)
	}
	if got != "CAST('2026-10-07 12:00:00' AS TIMESTAMP) CAST('2026-10-07 13:00:00' AS TIMESTAMP)" {
		t.Fatalf("got %s", got)
	}
}

func TestExpandMacros_RejectsAColumnThatIsNotAnIdentifier(t *testing.T) {
	for _, bad := range []string{"$__timeFilter()", "$__timeFilter(a b)", "$__timeFilter(1=1 OR x)", "$__timeFilter(ts; DROP TABLE t)", "$__timeFilter(a,b)"} {
		_, err := ExpandMacros(bad, tr)
		if err == nil || !strings.Contains(err.Error(), "timeFilter") {
			t.Fatalf("%q: want an error naming $__timeFilter, got %v", bad, err)
		}
	}
}

func TestExpandMacros_AnUnterminatedMacroIsAnError(t *testing.T) {
	if _, err := ExpandMacros("WHERE $__timeFilter(ts", tr); err == nil {
		t.Fatal("want an error")
	}
}
