package plugin

import (
	"fmt"
	"regexp"
	"strings"
	"time"

	"github.com/grafana/grafana-plugin-sdk-go/backend"
)

// Macros let one saved query follow the dashboard's time picker. They are expanded here, in the
// backend, not in the browser, so a query behaves the same when an alert rule runs it.
//
//	$__timeFrom()          the start of the time range, as CAST('...' AS TIMESTAMP)
//	$__timeTo()            the end of the time range
//	$__timeFilter(col)     col >= <from> AND col <= <to>
//
// Times are written in UTC as 'YYYY-MM-DD HH:MM:SS', because that is how IRIS renders and compares
// %TimeStamp values on a server whose clock is UTC (as containers are). A server on local time needs
// the column converted in the query; the data source does not guess.
//
// Grafana's own built-in variables ($__interval, $__from, ...) and dashboard variables are replaced in
// the browser before the query is sent, so they are left alone here.

const iristime = "2006-01-02 15:04:05"

var (
	// An identifier IRIS accepts as a column: optional table qualifiers, or a double-quoted name.
	columnPattern = regexp.MustCompile(`^(?:[A-Za-z_%][A-Za-z0-9_%]*|"[^"]+")(?:\.(?:[A-Za-z_%][A-Za-z0-9_%]*|"[^"]+"))*$`)
	filterPattern = regexp.MustCompile(`\$__timeFilter\(([^)]*)\)`)
	filterOpen    = regexp.MustCompile(`\$__timeFilter\(`)
)

// timestampLiteral is CAST('...' AS TIMESTAMP), not a bare string. Measured on a real IRIS: a bare
// string literal compares correctly with a DATETIME column but silently matches NOTHING against a
// TIMESTAMP column made by DDL (stored as a PosixTime number), while the CAST form is right for both.
func timestampLiteral(t time.Time) string {
	return "CAST('" + t.UTC().Format(iristime) + "' AS TIMESTAMP)"
}

// ExpandMacros replaces the time macros in sql using the query's time range.
func ExpandMacros(sql string, tr backend.TimeRange) (string, error) {
	from := timestampLiteral(tr.From)
	to := timestampLiteral(tr.To)

	// Every opening "$__timeFilter(" must close, or the regex below would silently skip it.
	if len(filterOpen.FindAllString(sql, -1)) != len(filterPattern.FindAllString(sql, -1)) {
		return "", fmt.Errorf("$__timeFilter( is not closed with )")
	}

	var expandErr error
	sql = filterPattern.ReplaceAllStringFunc(sql, func(m string) string {
		col := strings.TrimSpace(filterPattern.FindStringSubmatch(m)[1])
		if !columnPattern.MatchString(col) {
			expandErr = fmt.Errorf("$__timeFilter needs one column name, got %q", col)
			return m
		}
		return fmt.Sprintf("%s >= %s AND %s <= %s", col, from, col, to)
	})
	if expandErr != nil {
		return "", expandErr
	}

	sql = strings.ReplaceAll(sql, "$__timeFrom()", from)
	sql = strings.ReplaceAll(sql, "$__timeTo()", to)
	return sql, nil
}
