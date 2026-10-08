package client

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
)

// These tests serve bytes captured from a real IRIS (testdata/), because the fakes in
// rest_client_test.go were written from the same assumptions as the code and so could not
// disagree with it. A SQL error from a real IRIS has status.errors as an array of OBJECTS.

func serveFixture(t *testing.T, name string) *RESTClient {
	t.Helper()
	body, err := os.ReadFile("testdata/" + name)
	if err != nil {
		t.Fatal(err)
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(body)
	}))
	t.Cleanup(srv.Close)
	return NewRESTClient(RESTClientConfig{BaseURL: srv.URL, Namespace: "USER", Username: "u", Password: "p"})
}

func TestQuery_RealIRISErrorObjectReachesTheUserAsIRISsOwnMessage(t *testing.T) {
	c := serveFixture(t, "query_error.json")

	_, err := c.Query(context.Background(), "SELECT * FROM No.Such")

	if err == nil {
		t.Fatal("want an error")
	}
	if strings.Contains(err.Error(), "decoding query response") || strings.Contains(err.Error(), "unmarshal") {
		t.Fatalf("the error object was not understood: %v", err)
	}
	if !strings.Contains(err.Error(), "IDENTIFIER expected") {
		t.Fatalf("want IRIS's own SQL message, got: %v", err)
	}
}

func TestQuery_RealIRISRowsKeepSelectOrderAndTypes(t *testing.T) {
	c := serveFixture(t, "query_ok.json")

	qr, err := c.Query(context.Background(), "SELECT ...")

	if err != nil {
		t.Fatal(err)
	}
	var names []string
	for _, col := range qr.Columns {
		names = append(names, col.Name)
	}
	if got := strings.Join(names, ","); got != "one,s,f,t,n,b" {
		t.Fatalf("columns in SELECT order, got %s", got)
	}
	if len(qr.Rows) != 1 || qr.Rows[0][1] != "x" {
		t.Fatalf("unexpected rows: %v", qr.Rows)
	}
	// A real IRIS sends NULL as "" (documented in docs/SPEC.md); the client must not turn it into nil.
	if qr.Rows[0][4] != "" {
		t.Fatalf("NULL arrives as an empty string on this path, got %#v", qr.Rows[0][4])
	}
}

func TestMetrics_RealIRISOutputParsesWithoutLoss(t *testing.T) {
	c := serveFixture(t, "metrics.txt")

	ms, err := c.Metrics(context.Background())

	if err != nil {
		t.Fatal(err)
	}
	if len(ms) < 500 {
		t.Fatalf("a real IRIS exposes hundreds of samples, parsed %d", len(ms))
	}
	for _, m := range ms {
		if m.Name == "" {
			t.Fatalf("a sample has no name: %+v", m)
		}
	}
}
