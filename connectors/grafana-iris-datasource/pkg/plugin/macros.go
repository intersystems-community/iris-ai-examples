package plugin

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/grafana/grafana-plugin-sdk-go/backend"
)

// Macros let one saved query follow the dashboard's time picker. They are expanded here, in the
// backend, not in the browser, so a query behaves the same when an alert rule runs it.
//
//	$__timeFrom()              the start of the time range, as CAST('...' AS TIMESTAMP)
//	$__timeTo()                the end of the time range
//	$__timeFrom(col)           col >= <from>
//	$__timeTo(col)             col <= <to>
//	$__timeFilter(col)         col >= <from> AND col <= <to>
//	$__timeGroup(col, step)    col floored to a whole number of steps, for GROUP BY on a time series;
//	                           step is 30s, 5m, 2h, 7d (or 500ms, rounded up to 1s), or $__interval
//
// Times are written in UTC as 'YYYY-MM-DD HH:MM:SS', because that is how IRIS renders and compares
// %TimeStamp values on a server whose clock is UTC (as containers are). A server on local time needs
// the column converted in the query; the data source does not guess.
//
// Grafana's own built-in variables ($__interval, $__from, ...) and dashboard variables are replaced in
// the browser before the query is sent, so they are left alone here.

const iristime = "2006-01-02 15:04:05"

// epoch is the origin for $__timeGroup. A CAST, not a bare {ts '...'} literal, to match timestampLiteral;
// measured on a real IRIS to bucket a PosixTime TIMESTAMP column and a DATETIME column alike.
const epoch = "CAST('1970-01-01 00:00:00' AS TIMESTAMP)"

var (
	// An identifier IRIS accepts as a column: optional table qualifiers, or a double-quoted name.
	columnPattern = regexp.MustCompile(`^(?:[A-Za-z_%][A-Za-z0-9_%]*|"[^"]+")(?:\.(?:[A-Za-z_%][A-Za-z0-9_%]*|"[^"]+"))*$`)
	macroOpen     = regexp.MustCompile(`\$__(timeFilter|timeFrom|timeTo|timeGroup)\(`)
	// A step such as 30s, 5m, 2h, 7d, 1500ms.
	intervalPattern = regexp.MustCompile(`^([0-9]+)(ms|s|m|h|d)$`)
	intervalUnits   = map[string]time.Duration{"ms": time.Millisecond, "s": time.Second, "m": time.Minute, "h": time.Hour, "d": 24 * time.Hour}
)

// timestampLiteral is CAST('...' AS TIMESTAMP), not a bare string. Measured on a real IRIS: a bare
// string literal compares correctly with a DATETIME column but silently matches NOTHING against a
// TIMESTAMP column made by DDL (stored as a PosixTime number), while the CAST form is right for both.
func timestampLiteral(t time.Time) string {
	return "CAST('" + t.UTC().Format(iristime) + "' AS TIMESTAMP)"
}

// ExpandMacros replaces the time macros in sql using the query's time range. interval is the query's
// step (Grafana's $__interval), used by $__timeGroup(col, $__interval); zero means none is available.
func ExpandMacros(sql string, tr backend.TimeRange, interval time.Duration) (string, error) {
	from := timestampLiteral(tr.From)
	to := timestampLiteral(tr.To)

	var out strings.Builder
	rest := sql
	for {
		loc := macroOpen.FindStringSubmatchIndex(rest)
		if loc == nil {
			out.WriteString(rest)
			return out.String(), nil
		}
		name := rest[loc[2]:loc[3]]
		argStart := loc[1]
		// Every opening "$__name(" must close, or the rest of the query would be silently swallowed.
		closeAt := strings.IndexByte(rest[argStart:], ')')
		if closeAt < 0 {
			return "", fmt.Errorf("$__%s( is not closed with )", name)
		}
		expanded, err := expandMacro(name, rest[argStart:argStart+closeAt], from, to, interval)
		if err != nil {
			return "", err
		}
		out.WriteString(rest[:loc[0]])
		out.WriteString(expanded)
		rest = rest[argStart+closeAt+1:]
	}
}

func expandMacro(name, args, from, to string, interval time.Duration) (string, error) {
	switch name {
	case "timeFilter":
		col, err := oneColumn(name, args)
		if err != nil {
			return "", err
		}
		return fmt.Sprintf("%s >= %s AND %s <= %s", col, from, col, to), nil
	case "timeFrom", "timeTo":
		bound := from
		op := ">="
		if name == "timeTo" {
			bound, op = to, "<="
		}
		if strings.TrimSpace(args) == "" {
			return bound, nil // the bare form is the timestamp itself
		}
		col, err := oneColumn(name, args)
		if err != nil {
			return "", err
		}
		return fmt.Sprintf("%s %s %s", col, op, bound), nil
	default: // timeGroup
		return expandTimeGroup(args, interval)
	}
}

func oneColumn(name, args string) (string, error) {
	col := strings.TrimSpace(args)
	if !columnPattern.MatchString(col) {
		return "", fmt.Errorf("$__%s needs one column name, got %q", name, col)
	}
	return col, nil
}

func expandTimeGroup(args string, interval time.Duration) (string, error) {
	parts := strings.Split(args, ",")
	if len(parts) != 2 {
		return "", fmt.Errorf("$__timeGroup needs a column and an interval, got %q", args)
	}
	col := strings.TrimSpace(parts[0])
	if !columnPattern.MatchString(col) {
		return "", fmt.Errorf("$__timeGroup needs a column name first, got %q", col)
	}
	seconds, err := intervalSeconds(strings.TrimSpace(parts[1]), interval)
	if err != nil {
		return "", err
	}
	n := strconv.FormatInt(seconds, 10)
	return fmt.Sprintf("DATEADD(second, FLOOR(DATEDIFF(second, %s, %s) / %s) * %s, %s)", epoch, col, n, n, epoch), nil
}

// intervalSeconds turns "5m" or "$__interval" into whole seconds, at least one. IRIS buckets at one-second
// resolution here, so a sub-second step is rounded up rather than refused.
func intervalSeconds(raw string, queryInterval time.Duration) (int64, error) {
	if raw == "$__interval" {
		if queryInterval <= 0 {
			return 0, fmt.Errorf("$__timeGroup interval $__interval has no value here; give an explicit step such as 1m")
		}
		return ceilSeconds(queryInterval), nil
	}
	m := intervalPattern.FindStringSubmatch(raw)
	if m == nil {
		return 0, fmt.Errorf("$__timeGroup interval %q is not a step such as 30s, 5m, 2h or 1d", raw)
	}
	n, err := strconv.ParseInt(m[1], 10, 64)
	if err != nil || n <= 0 {
		return 0, fmt.Errorf("$__timeGroup interval %q must be greater than zero", raw)
	}
	return ceilSeconds(time.Duration(n) * intervalUnits[m[2]]), nil
}

func ceilSeconds(d time.Duration) int64 {
	s := int64((d + time.Second - 1) / time.Second)
	if s < 1 {
		return 1
	}
	return s
}
