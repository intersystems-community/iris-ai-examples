package plugin

import (
	"strings"
	"unicode"
)

// Why this exists: Grafana lets anyone who can edit a panel type any SQL, and the plugin reaches IRIS through
// its REST API, which was measured NOT to apply table-level SQL privileges (a SELECT-only account could
// DELETE rows through it). IRIS permissions therefore cannot be what keeps a dashboard from changing data, so
// the plugin refuses anything that is not a query unless the data source's "Allow data changes" setting is on.
//
// This is a guard against mistakes and casual misuse, not a security boundary against a determined user: a
// query can still call a function that has side effects. The real protection is a dedicated IRIS instance or
// namespace, and network access limited to Grafana.

const refusal = "this data source is read-only: only SELECT queries (or WITH ... SELECT) run. Turn on \"Allow data changes\" in the data source settings to run other statements"

// IsReadOnly reports whether sql is a single SELECT (or WITH ... SELECT) statement. The second result says why
// not, in words fit to show the user.
func IsReadOnly(sql string) (bool, string) {
	code := stripCommentsAndLiterals(sql)
	code = strings.TrimSpace(code)
	code = strings.TrimRight(code, "; \t\r\n")
	if code == "" {
		return false, "the query is empty; " + refusal
	}
	if strings.Contains(code, ";") {
		return false, "more than one statement in a query; " + refusal
	}
	first := firstWord(strings.TrimLeft(code, "( \t\r\n"))
	switch strings.ToUpper(first) {
	case "SELECT", "WITH":
		return true, ""
	}
	return false, refusal
}

// stripCommentsAndLiterals returns sql with -- and /* */ comments removed and the contents of '...' strings and
// "..." identifiers blanked, so a keyword or semicolon inside them is not mistaken for code. A doubled quote
// inside a string is an escaped quote.
func stripCommentsAndLiterals(sql string) string {
	var out strings.Builder
	rs := []rune(sql)
	for i := 0; i < len(rs); i++ {
		c := rs[i]
		switch {
		case c == '-' && i+1 < len(rs) && rs[i+1] == '-':
			for i < len(rs) && rs[i] != '\n' {
				i++
			}
			out.WriteRune('\n')
		case c == '/' && i+1 < len(rs) && rs[i+1] == '*':
			i += 2
			for i+1 < len(rs) && !(rs[i] == '*' && rs[i+1] == '/') {
				i++
			}
			i++ // past the closing slash
			out.WriteRune(' ')
		case c == '\'' || c == '"':
			quote := c
			out.WriteRune(quote)
			i++
			for i < len(rs) {
				if rs[i] == quote {
					if i+1 < len(rs) && rs[i+1] == quote {
						i += 2
						continue
					}
					break
				}
				i++
			}
			out.WriteRune(quote)
		default:
			out.WriteRune(c)
		}
	}
	return out.String()
}

func firstWord(s string) string {
	end := 0
	for end < len(s) && (unicode.IsLetter(rune(s[end])) || s[end] == '_' || s[end] == '%') {
		end++
	}
	return s[:end]
}
