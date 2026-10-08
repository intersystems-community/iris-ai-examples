//go:build e2e

package client

import (
	"context"
	"os"
	"strings"
	"testing"
	"time"
)

// Real-IRIS tests (PA-02). Start the container first:
//
//	docker compose -f docker-compose.e2e.yaml up -d --wait
//	IRIS_URL=http://localhost:33273 IRIS_USER=_SYSTEM IRIS_PASSWORD=SYS go test -tags e2e ./pkg/plugin/client/
//
// A missing variable FAILS the run. A skipped real-IRIS test is how this plugin went unverified.

func realClient(t *testing.T, mutate ...func(*RESTClientConfig)) *RESTClient {
	t.Helper()
	cfg := RESTClientConfig{
		BaseURL:   os.Getenv("IRIS_URL"),
		Namespace: "USER",
		Username:  os.Getenv("IRIS_USER"),
		Password:  os.Getenv("IRIS_PASSWORD"),
		Timeout:   30 * time.Second,
	}
	if cfg.BaseURL == "" || cfg.Username == "" || cfg.Password == "" {
		t.Fatal("set IRIS_URL, IRIS_USER and IRIS_PASSWORD (see the comment at the top of this file)")
	}
	for _, m := range mutate {
		m(&cfg)
	}
	return NewRESTClient(cfg)
}

func TestE2E_PingAndHealth(t *testing.T) {
	if err := realClient(t).Ping(context.Background()); err != nil {
		t.Fatal(err)
	}
}

func TestE2E_QueryReturnsColumnsInSelectOrder(t *testing.T) {
	qr, err := realClient(t).Query(context.Background(), "SELECT 1 AS one, 'x' AS s, 2.5 AS f, 3 AS b")
	if err != nil {
		t.Fatal(err)
	}
	var names []string
	for _, c := range qr.Columns {
		names = append(names, c.Name)
	}
	if got := strings.Join(names, ","); got != "one,s,f,b" {
		t.Fatalf("columns: %s", got)
	}
}

func TestE2E_SQLErrorCarriesIRISsOwnMessage(t *testing.T) {
	_, err := realClient(t).Query(context.Background(), "SELECT * FROM No.Such")
	if err == nil || !strings.Contains(err.Error(), "SQLCODE") {
		t.Fatalf("want IRIS's SQL error text, got %v", err)
	}
}

func TestE2E_NullArrivesAsEmptyOrZeroNotNil(t *testing.T) {
	// Documents what this transport can and cannot say (docs/SPEC.md): NULL is not distinguishable.
	qr, err := realClient(t).Query(context.Background(), "SELECT 1 AS v UNION ALL SELECT NULL")
	if err != nil {
		t.Fatal(err)
	}
	for _, row := range qr.Rows {
		if row[0] == nil {
			t.Fatalf("IRIS sent a JSON null; the documented behaviour has changed: %v", qr.Rows)
		}
	}
}

func TestE2E_FiveThousandRowsComeBackWhole(t *testing.T) {
	qr, err := realClient(t).Query(context.Background(), "SELECT TOP 5000 ID FROM %Dictionary.ClassDefinition")
	if err != nil {
		t.Fatal(err)
	}
	if len(qr.Rows) != 5000 {
		t.Fatalf("rows: %d", len(qr.Rows))
	}
}

func TestE2E_BadPasswordIsAnAuthenticationError(t *testing.T) {
	c := realClient(t, func(cfg *RESTClientConfig) { cfg.Password = "definitely-wrong" })
	_, err := c.Query(context.Background(), "SELECT 1")
	if err == nil || !strings.Contains(err.Error(), "authentication") {
		t.Fatalf("want an authentication error, got %v", err)
	}
}

func TestE2E_MissingNamespaceIsAnError(t *testing.T) {
	c := realClient(t, func(cfg *RESTClientConfig) { cfg.Namespace = "NOSUCHNS" })
	if _, err := c.Query(context.Background(), "SELECT 1"); err == nil {
		t.Fatal("want an error for a namespace that does not exist")
	}
}

func TestE2E_MetricsParse(t *testing.T) {
	ms, err := realClient(t).Metrics(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(ms) < 100 {
		t.Fatalf("a real IRIS exposes hundreds of samples, parsed %d", len(ms))
	}
	for _, m := range ms {
		if m.Name == "" {
			t.Fatalf("a sample has no name: %+v", m)
		}
	}
}
