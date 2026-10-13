package plugin

import (
	"strconv"
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
			got, err := ExpandMacros(c.in, tr, 0)
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

	got, err := ExpandMacros("$__timeFrom() $__timeTo()", r, 0)

	if err != nil {
		t.Fatal(err)
	}
	if got != "CAST('2026-10-07 12:00:00' AS TIMESTAMP) CAST('2026-10-07 13:00:00' AS TIMESTAMP)" {
		t.Fatalf("got %s", got)
	}
}

func TestExpandMacros_RejectsAColumnThatIsNotAnIdentifier(t *testing.T) {
	for _, bad := range []string{"$__timeFilter()", "$__timeFilter(a b)", "$__timeFilter(1=1 OR x)", "$__timeFilter(ts; DROP TABLE t)", "$__timeFilter(a,b)"} {
		_, err := ExpandMacros(bad, tr, 0)
		if err == nil || !strings.Contains(err.Error(), "timeFilter") {
			t.Fatalf("%q: want an error naming $__timeFilter, got %v", bad, err)
		}
	}
}

func TestExpandMacros_AnUnterminatedMacroIsAnError(t *testing.T) {
	if _, err := ExpandMacros("WHERE $__timeFilter(ts", tr, 0); err == nil {
		t.Fatal("want an error")
	}
}

const epochTS = "CAST('1970-01-01 00:00:00' AS TIMESTAMP)"

// bucket is what $__timeGroup(col, <n seconds>) must expand to: the column floored to a whole number of
// n-second steps since the epoch. Measured on a real IRIS to work on both a PosixTime TIMESTAMP column
// and a DATETIME column when the epoch is a CAST (the bare {ts ...} form is not used).
func bucket(col string, seconds int) string {
	n := strconv.Itoa(seconds)
	return "DATEADD(second, FLOOR(DATEDIFF(second, " + epochTS + ", " + col + ") / " + n + ") * " + n + ", " + epochTS + ")"
}

func TestExpandMacros_TimeFromAndToTakeAnOptionalColumn(t *testing.T) {
	cases := []struct{ in, want string }{
		{"WHERE $__timeFrom(ts)", "WHERE ts >= CAST('2026-10-07 12:00:00' AS TIMESTAMP)"},
		{"WHERE $__timeTo(ts)", "WHERE ts <= CAST('2026-10-07 13:30:15' AS TIMESTAMP)"},
		{"WHERE $__timeFrom( t.At )", "WHERE t.At >= CAST('2026-10-07 12:00:00' AS TIMESTAMP)"},
		{"x $__timeFrom() y", "x CAST('2026-10-07 12:00:00' AS TIMESTAMP) y"},
	}
	for _, c := range cases {
		got, err := ExpandMacros(c.in, tr, 0)
		if err != nil || got != c.want {
			t.Fatalf("%q\n got: %s (%v)\nwant: %s", c.in, got, err, c.want)
		}
	}
}

func TestExpandMacros_TimeFromAndToRejectANonColumn(t *testing.T) {
	for _, bad := range []string{"$__timeFrom(1=1 OR x)", "$__timeTo(a b)", "$__timeFrom(a,b)"} {
		if _, err := ExpandMacros(bad, tr, 0); err == nil {
			t.Fatalf("%q: want an error", bad)
		}
	}
}

func TestExpandMacros_TimeGroupBucketsByTheInterval(t *testing.T) {
	cases := []struct {
		interval string
		seconds  int
	}{
		{"30s", 30}, {"1m", 60}, {"5m", 300}, {"2h", 7200}, {"1d", 86400}, {"7d", 604800},
		{"500ms", 1}, {"1500ms", 2}, // a sub-second step cannot exist at one-second resolution, so round up
	}
	for _, c := range cases {
		got, err := ExpandMacros("SELECT $__timeGroup(ts, "+c.interval+")", tr, 0)
		if err != nil {
			t.Fatalf("%s: %v", c.interval, err)
		}
		if want := "SELECT " + bucket("ts", c.seconds); got != want {
			t.Fatalf("%s\n got: %s\nwant: %s", c.interval, got, want)
		}
	}
}

func TestExpandMacros_TimeGroupInIntervalUsesTheQueryInterval(t *testing.T) {
	got, err := ExpandMacros("$__timeGroup(ts, $__interval)", tr, 90*time.Second)
	if err != nil {
		t.Fatal(err)
	}
	if got != bucket("ts", 90) {
		t.Fatalf("got %s", got)
	}
}

func TestExpandMacros_TimeGroupIsExpandedEverywhereItAppears(t *testing.T) {
	got, err := ExpandMacros("SELECT $__timeGroup(ts, 1m) b FROM t GROUP BY $__timeGroup(ts, 1m)", tr, 0)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Count(got, bucket("ts", 60)) != 2 || strings.Contains(got, "$__") {
		t.Fatalf("got %s", got)
	}
}

func TestExpandMacros_TimeGroupRejectsBadArguments(t *testing.T) {
	cases := []struct{ in, why string }{
		{"$__timeGroup(ts)", "needs a column and an interval"},
		{"$__timeGroup(ts, 1m, 2m)", "needs a column and an interval"},
		{"$__timeGroup(a b, 1m)", "column"},
		{"$__timeGroup(ts, 7x)", "interval"},
		{"$__timeGroup(ts, 0s)", "interval"},
		{"$__timeGroup(ts, -5m)", "interval"},
		{"$__timeGroup(ts, 1m; DROP TABLE t)", "interval"},
		{"$__timeGroup(ts, $__interval)", "interval"}, // no query interval available (interval 0)
		{"$__timeGroup(ts, 1m", "not closed"},
	}
	for _, c := range cases {
		_, err := ExpandMacros(c.in, tr, 0)
		if err == nil || !strings.Contains(err.Error(), "timeGroup") || !strings.Contains(err.Error(), c.why) {
			t.Fatalf("%q: want an error naming $__timeGroup and %q, got %v", c.in, c.why, err)
		}
	}
}
