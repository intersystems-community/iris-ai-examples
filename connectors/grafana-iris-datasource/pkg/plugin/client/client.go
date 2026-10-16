// Package client defines the seam between the Grafana IRIS datasource
// plugin and InterSystems IRIS itself.
//
// Go has no native (cgo-free) IRIS driver. Three access paths were
// evaluated for this plugin (see /STATUS.md and /README.md at the module
// root for the full write-up):
//
//  1. IRIS's REST/SQL endpoint (the %Api.Atelier "action/query" call) over
//     plain HTTP on the web port (52773 by default). Pure Go, stdlib
//     net/http + encoding/json only. No cgo, no JVM, no extra runtime.
//  2. The PostgreSQL wire protocol via the community `iris-pgwire` gateway
//     plus a Go pgx driver. Pure Go, but requires an extra IRIS-side
//     process (`iris-pgwire`) that is not part of a stock IRIS install and
//     is not guaranteed to be running on a customer's instance.
//  3. A JDBC bridge (shell out to a JVM running the InterSystems JDBC
//     driver, e.g. via a sidecar or `avatica`-style thin server). Not pure
//     Go, requires a JVM at runtime, and Grafana backend plugins are
//     expected to be single static Go binaries.
//
// This plugin implements (1) as IRISClient's only production
// implementation (see rest_client.go), because it is the only option that
// works against a stock IRIS install with nothing extra to deploy, using
// only the Go standard library. The interface below is what keeps that
// decision swappable: a pgwire- or JDBC-backed IRISClient can be added
// later without touching the datasource, query, or frame-conversion code.
package client

import "context"

// Column describes one column of a QueryResult.
type Column struct {
	// Name is the column name as returned by IRIS.
	Name string
	// SQLType is the best-effort IRIS/JDBC type name for the column, when
	// the transport can report one. The REST/SQL transport does not carry
	// per-column type metadata on the plain (non-positional) query call, so
	// this is usually empty and callers should fall back to inferring the
	// type from the values themselves (see pkg/plugin/frame.go).
	SQLType string
}

// Row is a single result row, one value per Column, in column order.
// Values are already JSON-decoded Go types: nil, bool, float64, string, or
// a nested map/slice for irregular columns.
type Row []interface{}

// QueryResult is the tabular result of a single SQL statement.
type QueryResult struct {
	Columns []Column
	Rows    []Row
}

// MetricSample is one labeled sample scraped from IRIS's SAM/Prometheus
// metrics endpoint (/api/monitor/metrics).
type MetricSample struct {
	Name   string
	Labels map[string]string
	Value  float64
}

// IRISClient is the interface every access path to IRIS must satisfy. The
// datasource, query handling, and data-frame conversion code depend only
// on this interface, never on a concrete transport.
type IRISClient interface {
	// Query executes a single SQL statement and returns its result set.
	Query(ctx context.Context, sql string) (*QueryResult, error)

	// Metrics scrapes IRIS's SAM/Prometheus metrics endpoint and returns
	// every sample found.
	Metrics(ctx context.Context) ([]MetricSample, error)

	// Ping verifies connectivity and credentials. It is the backing call
	// for the plugin's health check.
	Ping(ctx context.Context) error
}
