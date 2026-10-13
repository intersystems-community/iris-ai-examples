package client

import "fmt"

// Typed errors, so the datasource can tell a user's bad SQL from a wrong password from an unreachable
// server from a fault in this plugin, and report each with the right status and error source. The
// messages are what the user reads in the panel.

// SQLError is IRIS rejecting the statement (status.errors in its response).
type SQLError struct {
	Message string
	Code    int
}

func (e *SQLError) Error() string { return "iris: query failed: " + e.Message }

// AuthError is HTTP 401 or 403 from IRIS or its web gateway, or a refused login on the native connection
// (HTTPStatus 0).
type AuthError struct{ HTTPStatus int }

func (e *AuthError) Error() string {
	if e.HTTPStatus == 0 {
		return "iris: authentication failed"
	}
	return fmt.Sprintf("iris: authentication failed (HTTP %d)", e.HTTPStatus)
}

// UnreachableError is a failure to talk to IRIS at all: refused, timed out, bad TLS.
type UnreachableError struct{ Err error }

func (e *UnreachableError) Error() string {
	return fmt.Sprintf("iris: could not reach the server: %v", e.Err)
}
func (e *UnreachableError) Unwrap() error { return e.Err }

// TooLargeError is a response over the configured limit; it is refused rather than buffered.
type TooLargeError struct{ Limit int64 }

func (e *TooLargeError) Error() string {
	return fmt.Sprintf("iris: the result is larger than %d bytes; narrow it with TOP, a WHERE clause or $__timeFilter", e.Limit)
}

// ConfigError is a request the data source's settings cannot satisfy, such as scraping metrics with no web
// port configured. It is the user's to fix in the data source settings.
type ConfigError struct{ Message string }

func (e *ConfigError) Error() string { return "iris: " + e.Message }

// TooManyRowsError is a result over the row cap; it is refused rather than held in memory.
type TooManyRowsError struct{ Limit int }

func (e *TooManyRowsError) Error() string {
	return fmt.Sprintf("iris: the result has more than %d rows; narrow it with TOP, a WHERE clause or $__timeFilter", e.Limit)
}
