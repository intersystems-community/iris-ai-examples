//go:build e2e

package client

import (
	"context"
	"errors"
	"fmt"
	"os"
	"reflect"
	"strings"
	"sync"
	"testing"
	"time"
)

// Tenant isolation against a real IRIS. The fixture, made as the admin user over REST: one events table
// holding two Tenants' rows, a view per Tenant, and a user per Tenant granted SELECT on its own view only
// (plus %Developer, without which /api/atelier refuses the login on either transport).

const (
	tenantTable = "GrafanaE2E.TenantEvents"
	acmeView    = "GrafanaE2E.AcmeEvents"
	globexView  = "GrafanaE2E.GlobexEvents"
)

var tenantUsers = map[string]string{"e2eacme": acmeView, "e2eglobex": globexView}

const tenantPassword = "e2e-tenant-pw"

var tenantOnce sync.Once

func tenantFixture(t *testing.T) {
	t.Helper()
	admin := realClient(t)
	ctx := context.Background()
	tenantOnce.Do(func() {
		for _, sql := range []string{"DROP VIEW " + acmeView, "DROP VIEW " + globexView, "DROP TABLE " + tenantTable, "DROP USER e2eacme", "DROP USER e2eglobex"} {
			_, _ = admin.Query(ctx, sql)
		}
		steps := []string{
			"CREATE TABLE " + tenantTable + " (TenantID VARCHAR(20), Kind VARCHAR(20), V INT)",
			"INSERT INTO " + tenantTable + " VALUES ('acme', 'deploy', 1)",
			"INSERT INTO " + tenantTable + " VALUES ('acme', 'restart', 2)",
			"INSERT INTO " + tenantTable + " VALUES ('globex', 'deploy', 3)",
			"CREATE VIEW " + acmeView + " AS SELECT TenantID, Kind, V FROM " + tenantTable + " WHERE TenantID = 'acme'",
			"CREATE VIEW " + globexView + " AS SELECT TenantID, Kind, V FROM " + tenantTable + " WHERE TenantID = 'globex'",
		}
		for user, view := range tenantUsers {
			steps = append(steps,
				"CREATE USER "+user+" IDENTIFY BY '"+tenantPassword+"'",
				"GRANT SELECT ON "+view+" TO "+user,
				"GRANT %Developer TO "+user)
		}
		for _, sql := range steps {
			if _, err := admin.Query(ctx, sql); err != nil {
				t.Fatalf("%s: %v", sql, err)
			}
		}
	})
}

func tenantTerminal(t *testing.T, user string) *TerminalClient {
	t.Helper()
	tenantFixture(t)
	return NewTerminalClient(TerminalClientConfig{BaseURL: os.Getenv("IRIS_URL"), Namespace: "USER", Username: user, Password: tenantPassword, Timeout: 30 * time.Second})
}

func wantPrivilegeRefusal(t *testing.T, what string, err error) {
	t.Helper()
	var sqlErr *SQLError
	if !errors.As(err, &sqlErr) || sqlErr.Code != -99 {
		t.Fatalf("%s: want SQLCODE -99, got %v", what, err)
	}
}

func TestTerminalE2E_ATenantUserReadsItsOwnViewAndNothingElse(t *testing.T) {
	for user, own := range tenantUsers {
		c := tenantTerminal(t, user)
		ctx := context.Background()
		res, err := c.Query(ctx, "SELECT TenantID, Kind, V FROM "+own+" ORDER BY V")
		if err != nil {
			t.Fatalf("%s reading %s: %v", user, own, err)
		}
		tenant := strings.TrimPrefix(user, "e2e")
		if len(res.Rows) == 0 {
			t.Fatalf("%s: no rows", user)
		}
		for _, row := range res.Rows {
			if row[0] != tenant {
				t.Fatalf("%s saw another Tenant's row: %v", user, row)
			}
		}
		for other := range tenantUsers {
			if view := tenantUsers[other]; view != own {
				_, err := c.Query(ctx, "SELECT * FROM "+view)
				wantPrivilegeRefusal(t, user+" reading "+view, err)
			}
		}
		_, err = c.Query(ctx, "SELECT * FROM "+tenantTable)
		wantPrivilegeRefusal(t, user+" reading the base table", err)
	}
}

func TestTerminalE2E_ATenantUserCannotChangeRows(t *testing.T) {
	c := tenantTerminal(t, "e2eacme")
	_, err := c.Query(context.Background(), "DELETE FROM "+acmeView)
	wantPrivilegeRefusal(t, "DELETE on its own view", err)
	if n := countTenantRows(t); n != 3 {
		t.Fatalf("the table has %d rows, want 3", n)
	}
}

func countTenantRows(t *testing.T) int {
	t.Helper()
	res, err := realClient(t).Query(context.Background(), "SELECT COUNT(*) AS n FROM "+tenantTable)
	if err != nil {
		t.Fatal(err)
	}
	return int(res.Rows[0][0].(float64))
}

func TestTerminalE2E_TheRESTPathLetsTheSameUserReadEverything(t *testing.T) {
	// Why the terminal transport exists. If this ever fails, /api/atelier has started checking privileges and
	// the README's comparison needs rewriting.
	tenantFixture(t)
	rest := realClient(t, func(c *RESTClientConfig) { c.Username, c.Password = "e2eacme", tenantPassword })
	res, err := rest.Query(context.Background(), "SELECT TenantID FROM "+tenantTable+" WHERE TenantID = 'globex'")
	if err != nil {
		t.Fatal(err)
	}
	if len(res.Rows) != 1 {
		t.Fatalf("over REST e2eacme read %d globex rows; the documented bypass has changed", len(res.Rows))
	}
}

func TestTerminalE2E_RowsReadTheSameAsTheRESTPath(t *testing.T) {
	admin := realClient(t)
	ctx := context.Background()
	const table = "GrafanaE2E.Types"
	_, _ = admin.Query(ctx, "DROP TABLE "+table)
	if _, err := admin.Query(ctx, "CREATE TABLE "+table+" (tp TIMESTAMP, td DATETIME, dd DATE, bi BIGINT, i INT, f DOUBLE, n NUMERIC(10,2), b BIT, s VARCHAR(20))"); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _, _ = admin.Query(ctx, "DROP TABLE "+table) })
	if _, err := admin.Query(ctx, "INSERT INTO "+table+" VALUES ('2026-10-07 12:00:00','2026-10-07 12:00:00',TO_DATE('2026-10-07','YYYY-MM-DD'),1791374400000,5,2.5,3.25,1,'é€ x')"); err != nil {
		t.Fatal(err)
	}
	if _, err := admin.Query(ctx, "INSERT INTO "+table+" (s) VALUES (NULL)"); err != nil {
		t.Fatal(err)
	}
	term := NewTerminalClient(TerminalClientConfig{BaseURL: os.Getenv("IRIS_URL"), Namespace: "USER", Username: os.Getenv("IRIS_USER"), Password: os.Getenv("IRIS_PASSWORD")})

	const q = "SELECT tp, td, dd, bi, i, f, n, b, s, -0.5 AS h FROM " + table + " WHERE s IS NOT NULL"
	viaREST, err := admin.Query(ctx, q)
	if err != nil {
		t.Fatal(err)
	}
	viaTerminal, err := term.Query(ctx, q)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(viaREST, viaTerminal) {
		t.Fatalf("REST     %#v\nterminal %#v", viaREST, viaTerminal)
	}

	// Where the two differ: REST cannot say NULL, the terminal can.
	nulls, err := term.Query(ctx, "SELECT tp, bi, s FROM "+table+" WHERE s IS NULL")
	if err != nil {
		t.Fatal(err)
	}
	for i, v := range nulls.Rows[0] {
		if v != nil {
			t.Fatalf("column %d: want nil for NULL, got %#v", i, v)
		}
	}
}

func TestTerminalE2E_ManyQueriesDoNotRunOutOfLicences(t *testing.T) {
	// Before the session cookie was shared, Community IRIS refused connections after a few dozen queries.
	c := tenantTerminal(t, "e2eacme")
	ctx := context.Background()
	for i := 0; i < 40; i++ {
		if _, err := c.Query(ctx, fmt.Sprintf("SELECT %d AS n", i)); err != nil {
			t.Fatalf("query %d: %v", i, err)
		}
	}
	var wg sync.WaitGroup
	errs := make(chan error, 8)
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, err := c.Query(ctx, "SELECT Kind FROM "+acmeView)
			errs <- err
		}()
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		if err != nil {
			t.Fatal(err)
		}
	}
}

func TestTerminalE2E_AWrongPasswordIsAnAuthError(t *testing.T) {
	tenantFixture(t)
	c := NewTerminalClient(TerminalClientConfig{BaseURL: os.Getenv("IRIS_URL"), Namespace: "USER", Username: "e2eacme", Password: "wrong"})
	_, err := c.Query(context.Background(), "SELECT 1")
	var auth *AuthError
	if !errors.As(err, &auth) {
		t.Fatalf("got %v", err)
	}
}

func TestTerminalE2E_ALongQueryRunsWhole(t *testing.T) {
	// Far past the terminal's 425-character line, so the chunking is exercised for real.
	c := tenantTerminal(t, "e2eacme")
	cols := make([]string, 300)
	for i := range cols {
		cols[i] = fmt.Sprintf("%d AS c%d", i, i)
	}
	res, err := c.Query(context.Background(), "SELECT "+strings.Join(cols, ", "))
	if err != nil {
		t.Fatal(err)
	}
	if len(res.Columns) != 300 || res.Rows[0][299] != 299.0 {
		t.Fatalf("got %d columns, last %v", len(res.Columns), res.Rows[0][len(res.Rows[0])-1])
	}
}
