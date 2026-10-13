//go:build e2e

package client

import (
	"context"
	"errors"
	"net"
	"os"
	"strconv"
	"testing"
	"time"
)

// Real-IRIS tests for the native (SuperServer) transport. Besides the variables in e2e_test.go they need the
// SuperServer address, e.g. IRIS_SUPERSERVER=192.168.215.4:1972 (the test container's IP on this machine; it
// does not publish 1972, see docker-compose.e2e.yaml). A missing variable FAILS the run.

func nativeConfig(t *testing.T) NativeClientConfig {
	t.Helper()
	addr := os.Getenv("IRIS_SUPERSERVER")
	if addr == "" || os.Getenv("IRIS_USER") == "" || os.Getenv("IRIS_PASSWORD") == "" {
		t.Fatal("set IRIS_SUPERSERVER (host:port), IRIS_USER and IRIS_PASSWORD (see the comment at the top of this file)")
	}
	host, portText, err := net.SplitHostPort(addr)
	if err != nil {
		t.Fatalf("IRIS_SUPERSERVER %q: %v", addr, err)
	}
	port, _ := strconv.Atoi(portText)
	return NativeClientConfig{Host: host, Port: port, Namespace: "USER", Username: os.Getenv("IRIS_USER"), Password: os.Getenv("IRIS_PASSWORD"), Timeout: 30 * time.Second}
}

func realNative(t *testing.T, mutate ...func(*NativeClientConfig)) *NativeClient {
	t.Helper()
	cfg := nativeConfig(t)
	for _, m := range mutate {
		m(&cfg)
	}
	c := NewNativeClient(cfg)
	t.Cleanup(func() { _ = c.Close() })
	return c
}

func seedNative(t *testing.T, c *NativeClient, table string) {
	t.Helper()
	ctx := context.Background()
	_, _ = c.Query(ctx, "DROP TABLE "+table)
	if _, err := c.Query(ctx, "CREATE TABLE "+table+" (tp TIMESTAMP, td DATETIME, n INTEGER, s VARCHAR(10))"); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _, _ = c.Query(ctx, "DROP TABLE "+table) })
	for i := 1; i <= 5; i++ {
		sql := "INSERT INTO " + table + " VALUES ('2026-10-07 12:00:10','2026-10-07 12:00:10'," + strconv.Itoa(i) + ",'x')"
		if _, err := c.Query(ctx, sql); err != nil {
			t.Fatal(err)
		}
	}
}

func TestNativeE2E_PingAndQuery(t *testing.T) {
	c := realNative(t)
	if err := c.Ping(context.Background()); err != nil {
		t.Fatal(err)
	}
	seedNative(t, c, "NE2E_Basics")

	got, err := c.Query(context.Background(), "SELECT n, s FROM NE2E_Basics ORDER BY n")

	if err != nil {
		t.Fatal(err)
	}
	if len(got.Rows) != 5 || len(got.Columns) != 2 || got.Columns[0].Name != "n" {
		t.Fatalf("unexpected result %+v", got)
	}
	if got.Rows[0][0] != float64(1) || got.Rows[0][1] != "x" {
		t.Fatalf("a number is a float64 and text a string, got %#v", got.Rows[0])
	}
}

func TestNativeE2E_BothKindsOfTimestampColumnComeBackAsTheSameUTCWallTime(t *testing.T) {
	c := realNative(t)
	seedNative(t, c, "NE2E_Times")

	got, err := c.Query(context.Background(), "SELECT TOP 1 tp, td FROM NE2E_Times")

	if err != nil {
		t.Fatal(err)
	}
	if got.Rows[0][0] != "2026-10-07 12:00:10" || got.Rows[0][1] != "2026-10-07 12:00:10" {
		t.Fatalf("the PosixTime column and the DATETIME column must both read 12:00:10 UTC, got %#v", got.Rows[0])
	}
}

func TestNativeE2E_ABadStatementIsASQLErrorWithIRISsCode(t *testing.T) {
	_, err := realNative(t).Query(context.Background(), "SELECT nope FROM No_Such_Table")

	var sqlErr *SQLError
	if !errors.As(err, &sqlErr) || sqlErr.Code != -30 {
		t.Fatalf("want SQLCODE -30 (table not found), got %#v", err)
	}
}

func TestNativeE2E_AWrongPasswordIsAnAuthError(t *testing.T) {
	c := realNative(t, func(cfg *NativeClientConfig) { cfg.Password = "definitely-wrong" })

	err := c.Ping(context.Background())

	var authErr *AuthError
	if !errors.As(err, &authErr) {
		t.Fatalf("want an AuthError, got %#v", err)
	}
}

func TestNativeE2E_ADeadPortIsUnreachable(t *testing.T) {
	c := realNative(t, func(cfg *NativeClientConfig) { cfg.Host, cfg.Port = "127.0.0.1", 1 })

	err := c.Ping(context.Background())

	var unreachable *UnreachableError
	if !errors.As(err, &unreachable) {
		t.Fatalf("want an UnreachableError, got %#v", err)
	}
}

func TestNativeE2E_ResultsOverTheRowCapAreRefused(t *testing.T) {
	c := realNative(t, func(cfg *NativeClientConfig) { cfg.MaxRows = 3 })
	seedNative(t, c, "NE2E_Cap")

	_, err := c.Query(context.Background(), "SELECT n FROM NE2E_Cap")

	var tooMany *TooManyRowsError
	if !errors.As(err, &tooMany) || tooMany.Limit != 3 {
		t.Fatalf("want a TooManyRowsError for limit 3, got %#v", err)
	}
}

// This is why the native transport exists. Over REST (/api/atelier) a SELECT-only account could DELETE and read
// %SYS, because that endpoint ignores SQL privileges. Over the SuperServer IRIS applies them.
func TestNativeE2E_ASelectOnlyAccountCannotChangeDataOrReadSystemTables(t *testing.T) {
	admin := realNative(t)
	seedNative(t, admin, "NE2E_Priv")
	ctx := context.Background()
	_, _ = admin.Query(ctx, "DROP USER ne2e_ro")
	if _, err := admin.Query(ctx, "CREATE USER ne2e_ro IDENTIFY BY ro123"); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _, _ = admin.Query(ctx, "DROP USER ne2e_ro") })
	if _, err := admin.Query(ctx, "GRANT SELECT ON NE2E_Priv TO ne2e_ro"); err != nil {
		t.Fatal(err)
	}
	ro := realNative(t, func(cfg *NativeClientConfig) { cfg.Username, cfg.Password = "ne2e_ro", "ro123" })

	if _, err := ro.Query(ctx, "SELECT COUNT(*) FROM NE2E_Priv"); err != nil {
		t.Fatalf("the granted SELECT must work: %v", err)
	}
	for _, denied := range []string{"DELETE FROM NE2E_Priv", "INSERT INTO NE2E_Priv (n) VALUES (99)", "SELECT COUNT(*) FROM %SYS.Task"} {
		_, err := ro.Query(ctx, denied)
		var sqlErr *SQLError
		if !errors.As(err, &sqlErr) || sqlErr.Code != -99 {
			t.Fatalf("%q: want a privilege violation (SQLCODE -99), got %#v", denied, err)
		}
	}
	left, _ := admin.Query(ctx, "SELECT COUNT(*) FROM NE2E_Priv")
	if left.Rows[0][0] != float64(5) {
		t.Fatalf("the refused statements must change nothing, %v rows left", left.Rows[0][0])
	}
}

func TestNativeE2E_AStatementWithNoResultSetStillRunsOnce(t *testing.T) {
	c := realNative(t)
	seedNative(t, c, "NE2E_Dml") // five INSERTs through Query, each of which has no result set

	got, err := c.Query(context.Background(), "SELECT COUNT(*) FROM NE2E_Dml")

	if err != nil {
		t.Fatal(err)
	}
	if got.Rows[0][0] != float64(5) {
		t.Fatalf("five inserts must give five rows, not run twice or not at all: %v", got.Rows[0][0])
	}
	del, err := c.Query(context.Background(), "DELETE FROM NE2E_Dml WHERE n > 3")
	if err != nil || len(del.Rows) != 0 {
		t.Fatalf("a DELETE returns an empty result, got %+v (%v)", del, err)
	}
	got, _ = c.Query(context.Background(), "SELECT COUNT(*) FROM NE2E_Dml")
	if got.Rows[0][0] != float64(3) {
		t.Fatalf("the DELETE must have taken effect, %v rows left", got.Rows[0][0])
	}
}

// go-irisnative v0.3.0 failed a whole query that returned a double with trailing zero bytes (0, 2.0, 0.5, an AVG
// that lands on a whole number). The fix lives in third_party/go-irisnative; see its PATCHES.md.
func TestNativeE2E_DoublesWithDroppedZeroBytesDecode(t *testing.T) {
	c := realNative(t)

	got, err := c.Query(context.Background(),
		"SELECT CAST(0 AS DOUBLE) AS a, CAST(2 AS DOUBLE) AS b, CAST(-2 AS DOUBLE) AS c, CAST(0.5 AS DOUBLE) AS d, CAST(123456789.125 AS DOUBLE) AS e, CAST(0.1 AS DOUBLE) AS f")

	if err != nil {
		t.Fatal(err)
	}
	want := []float64{0, 2, -2, 0.5, 123456789.125, 0.1}
	for i, w := range want {
		if got.Rows[0][i] != w {
			t.Errorf("column %s = %v, want %v", got.Columns[i].Name, got.Rows[0][i], w)
		}
	}
}
