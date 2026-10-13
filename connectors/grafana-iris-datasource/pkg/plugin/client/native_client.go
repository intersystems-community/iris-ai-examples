package client

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"net"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/caretdev/go-irisnative/src/connection"

	// Registers the "iris" database/sql driver: pure Go, so the plugin stays one static binary.
	_ "github.com/caretdev/go-irisnative"
)

// DefaultMaxRows is generous for a dashboard query and finite for a runaway SELECT *.
const DefaultMaxRows = 1_000_000

// NativeClientConfig configures a NativeClient.
type NativeClientConfig struct {
	// Host and Port are the IRIS SuperServer, usually 1972; not the web server port.
	Host      string
	Port      int
	Namespace string
	Username  string
	Password  string
	// Timeout bounds one query; 0 means none.
	Timeout time.Duration
	// MaxOpenConns, MaxIdleConns and ConnMaxLifetime tune the connection pool; zero keeps database/sql's default.
	MaxOpenConns    int
	MaxIdleConns    int
	ConnMaxLifetime time.Duration
	// MaxRows caps the rows read for one query; 0 means DefaultMaxRows.
	MaxRows int
	// Metrics scrapes /api/monitor/metrics, which exists only on the web server. Nil means metrics are
	// unavailable on this connection.
	Metrics IRISClient
}

// NativeClient is an IRISClient that talks to the IRIS SuperServer with the community go-irisnative driver
// (pure Go, over database/sql). Unlike the REST path it runs under the SQL privileges of the account:
// a SELECT-only user cannot INSERT, DELETE or read %SYS, which /api/atelier does not enforce.
//
// The driver is alpha and has no TLS option, so the connection is not encrypted on the wire.
type NativeClient struct {
	cfg NativeClientConfig
	db  *sql.DB
	// initErr is a failure to open the pool; it is reported on first use.
	initErr error
}

var _ IRISClient = (*NativeClient)(nil)

// NewNativeClient builds the pool lazily: database/sql connects on first use.
func NewNativeClient(cfg NativeClientConfig) *NativeClient {
	db, err := sql.Open("iris", nativeDSN(cfg))
	if err != nil {
		return &NativeClient{cfg: cfg, initErr: err}
	}
	if cfg.MaxOpenConns > 0 {
		db.SetMaxOpenConns(cfg.MaxOpenConns)
	}
	if cfg.MaxIdleConns > 0 {
		db.SetMaxIdleConns(cfg.MaxIdleConns)
	}
	if cfg.ConnMaxLifetime > 0 {
		db.SetConnMaxLifetime(cfg.ConnMaxLifetime)
	}
	return &NativeClient{cfg: cfg, db: db}
}

// nativeDSN is iris://user:password@host:port/NAMESPACE?query_timeout=N, with the credentials escaped.
func nativeDSN(cfg NativeClientConfig) string {
	u := url.URL{
		Scheme: "iris",
		User:   url.UserPassword(cfg.Username, cfg.Password),
		Host:   net.JoinHostPort(cfg.Host, strconv.Itoa(cfg.Port)),
		Path:   "/" + cfg.Namespace,
	}
	if cfg.Timeout > 0 {
		u.RawQuery = url.Values{"query_timeout": {strconv.Itoa(int((cfg.Timeout + time.Second - 1) / time.Second))}}.Encode()
	}
	return u.String()
}

// Close releases the connection pool.
func (c *NativeClient) Close() error {
	if c.db == nil {
		return nil
	}
	return c.db.Close()
}

func (c *NativeClient) queryContext(ctx context.Context) (context.Context, context.CancelFunc) {
	if c.cfg.Timeout > 0 {
		return context.WithTimeout(ctx, c.cfg.Timeout)
	}
	return ctx, func() {}
}

// Query runs one SQL statement and returns every row, up to the row cap.
func (c *NativeClient) Query(ctx context.Context, query string) (*QueryResult, error) {
	if c.initErr != nil {
		return nil, mapNativeError(c.initErr)
	}
	ctx, cancel := c.queryContext(ctx)
	defer cancel()

	rows, err := c.db.QueryContext(ctx, query)
	if err != nil {
		return nil, mapNativeError(err)
	}
	defer rows.Close()

	types, err := rows.ColumnTypes()
	if err != nil {
		return nil, mapNativeError(err)
	}
	if len(types) == 0 {
		// INSERT, UPDATE, DELETE and DDL: the driver has already run the statement, but trying to fetch rows
		// from it fails on the server (<UNDEFINED> in %SYS.DBSRV), so do not.
		return &QueryResult{}, nil
	}
	result := &QueryResult{Columns: make([]Column, len(types))}
	for i, t := range types {
		result.Columns[i] = Column{Name: t.Name(), SQLType: t.DatabaseTypeName()}
	}

	maxRows := c.cfg.MaxRows
	if maxRows <= 0 {
		maxRows = DefaultMaxRows
	}
	for rows.Next() {
		if len(result.Rows) >= maxRows {
			return nil, &TooManyRowsError{Limit: maxRows}
		}
		values := make([]any, len(types))
		pointers := make([]any, len(types))
		for i := range values {
			pointers[i] = &values[i]
		}
		if err := rows.Scan(pointers...); err != nil {
			return nil, mapNativeError(err)
		}
		row := make(Row, len(values))
		for i, v := range values {
			row[i] = convertNativeValue(v)
		}
		result.Rows = append(result.Rows, row)
	}
	if err := rows.Err(); err != nil {
		return nil, mapNativeError(err)
	}
	return result, nil
}

// Metrics scrapes through the web-port client, since /api/monitor/metrics is served by the web server.
func (c *NativeClient) Metrics(ctx context.Context) ([]MetricSample, error) {
	if c.cfg.Metrics == nil {
		return nil, &ConfigError{Message: "SAM metrics are served by the IRIS web server; set the web port in the data source settings to use them over a native connection"}
	}
	return c.cfg.Metrics.Metrics(ctx)
}

// Ping verifies the connection and the credentials.
func (c *NativeClient) Ping(ctx context.Context) error {
	if c.initErr != nil {
		return mapNativeError(c.initErr)
	}
	ctx, cancel := c.queryContext(ctx)
	defer cancel()
	return mapNativeError(c.db.PingContext(ctx))
}

// convertNativeValue turns a driver value into the JSON-like types the REST path yields, so frame
// conversion is the same for both transports: numbers are float64, times are UTC wall-clock strings.
func convertNativeValue(v any) any {
	switch x := v.(type) {
	case nil, string, bool, float64:
		return v
	case int:
		return float64(x)
	case int8:
		return float64(x)
	case int16:
		return float64(x)
	case int32:
		return float64(x)
	case int64:
		return float64(x)
	case uint8:
		return float64(x)
	case uint16:
		return float64(x)
	case uint32:
		return float64(x)
	case uint64:
		return float64(x)
	case float32:
		return float64(x)
	case []byte:
		return string(x)
	case time.Time:
		return x.UTC().Format("2006-01-02 15:04:05.999999")
	default:
		return fmt.Sprint(x)
	}
}

// mapNativeError sorts a driver error into the typed errors the datasource classifies.
func mapNativeError(err error) error {
	if err == nil {
		return nil
	}
	var sqlErr *connection.SQLError
	var netErr net.Error
	switch {
	case errors.As(err, &sqlErr):
		return &SQLError{Message: sqlErr.Message, Code: sqlCode(sqlErr.SQLCode)}
	case strings.Contains(strings.ToLower(err.Error()), "access denied"):
		return &AuthError{} // no HTTP status: this is not an HTTP transport
	case errors.Is(err, context.DeadlineExceeded), errors.As(err, &netErr):
		return &UnreachableError{Err: err}
	default:
		return err
	}
}

// sqlCode restores the sign. The driver reports the magnitude (30 for "table not found") where IRIS and the
// REST path say SQLCODE -30; 100, "no data", is the one positive code.
func sqlCode(driverCode int16) int {
	if driverCode > 0 && driverCode != 100 {
		return -int(driverCode)
	}
	return int(driverCode)
}
