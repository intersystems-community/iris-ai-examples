package client

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

// atelierQueryResponse mirrors the shape documented for
// POST /api/atelier/v1/{namespace}/action/query — see the package doc
// comment in client.go and README.md for sourcing. "content" is an array
// of JSON objects, one per row, keyed by column name.
type atelierQueryResponse struct {
	Status struct {
		Errors  []string `json:"errors"`
		Summary string   `json:"summary"`
	} `json:"status"`
	Console []string `json:"console"`
	Result  struct {
		Content []map[string]interface{} `json:"content"`
	} `json:"result"`
}

func newFakeIRISServer(t *testing.T, wantNamespace string, rows []map[string]interface{}, apiErr string) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/api/atelier/v1/"+wantNamespace+"/action/query":
			if r.Method != http.MethodPost {
				t.Errorf("expected POST, got %s", r.Method)
			}
			if ct := r.Header.Get("Content-Type"); ct != "application/json" {
				t.Errorf("expected Content-Type: application/json, got %q", ct)
			}
			user, pass, ok := r.BasicAuth()
			if !ok || user != "grafana" || pass != "secretpw" {
				w.WriteHeader(http.StatusUnauthorized)
				return
			}
			var body struct {
				Query string `json:"query"`
			}
			if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
				t.Fatalf("bad request body: %v", err)
			}
			resp := atelierQueryResponse{}
			if apiErr != "" {
				resp.Status.Errors = []string{apiErr}
				resp.Status.Summary = apiErr
			} else {
				resp.Result.Content = rows
			}
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(resp)
		case r.URL.Path == "/api/monitor/metrics":
			w.Header().Set("Content-Type", "text/plain; version=0.0.4")
			_, _ = w.Write([]byte("# HELP iris_up whether IRIS is up\n" +
				"# TYPE iris_up gauge\n" +
				"iris_up{instance=\"IRIS\"} 1\n" +
				"iris_global_refs_total 12345\n"))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
}

func testConfig(baseURL string) RESTClientConfig {
	return RESTClientConfig{
		BaseURL:   baseURL,
		Namespace: "USER",
		Username:  "grafana",
		Password:  "secretpw",
		Timeout:   5 * time.Second,
	}
}

func TestRESTClient_Query_Success(t *testing.T) {
	rows := []map[string]interface{}{
		{"ID": float64(1), "Name": "Maria Gonzalez", "Active": true},
		{"ID": float64(2), "Name": "John Smith", "Active": false},
	}
	srv := newFakeIRISServer(t, "USER", rows, "")
	defer srv.Close()

	c := NewRESTClient(testConfig(srv.URL))
	result, err := c.Query(context.Background(), "SELECT ID, Name, Active FROM Patient")
	if err != nil {
		t.Fatalf("Query returned error: %v", err)
	}
	if len(result.Rows) != 2 {
		t.Fatalf("expected 2 rows, got %d", len(result.Rows))
	}
	if len(result.Columns) != 3 {
		t.Fatalf("expected 3 columns, got %d: %+v", len(result.Columns), result.Columns)
	}
}

func TestRESTClient_Query_APIError(t *testing.T) {
	srv := newFakeIRISServer(t, "USER", nil, "SQLCODE -400: bad table name")
	defer srv.Close()

	c := NewRESTClient(testConfig(srv.URL))
	_, err := c.Query(context.Background(), "SELECT * FROM NoSuchTable")
	if err == nil {
		t.Fatal("expected an error, got nil")
	}
}

func TestRESTClient_Query_AuthFailure(t *testing.T) {
	rows := []map[string]interface{}{{"X": float64(1)}}
	srv := newFakeIRISServer(t, "USER", rows, "")
	defer srv.Close()

	cfg := testConfig(srv.URL)
	cfg.Password = "wrong"
	c := NewRESTClient(cfg)
	_, err := c.Query(context.Background(), "SELECT 1")
	if err == nil {
		t.Fatal("expected an auth error, got nil")
	}
}

func TestRESTClient_Query_EmptyResult(t *testing.T) {
	srv := newFakeIRISServer(t, "USER", []map[string]interface{}{}, "")
	defer srv.Close()

	c := NewRESTClient(testConfig(srv.URL))
	result, err := c.Query(context.Background(), "SELECT * FROM Patient WHERE 1=0")
	if err != nil {
		t.Fatalf("Query returned error: %v", err)
	}
	if len(result.Rows) != 0 {
		t.Fatalf("expected 0 rows, got %d", len(result.Rows))
	}
}

func TestRESTClient_Ping(t *testing.T) {
	rows := []map[string]interface{}{{"1": float64(1)}}
	srv := newFakeIRISServer(t, "USER", rows, "")
	defer srv.Close()

	c := NewRESTClient(testConfig(srv.URL))
	if err := c.Ping(context.Background()); err != nil {
		t.Fatalf("Ping returned error: %v", err)
	}
}

func TestRESTClient_Metrics(t *testing.T) {
	srv := newFakeIRISServer(t, "USER", nil, "")
	defer srv.Close()

	c := NewRESTClient(testConfig(srv.URL))
	samples, err := c.Metrics(context.Background())
	if err != nil {
		t.Fatalf("Metrics returned error: %v", err)
	}
	if len(samples) != 2 {
		t.Fatalf("expected 2 samples, got %d: %+v", len(samples), samples)
	}
}

// TestRESTClient_Query_PreservesColumnOrder pins down that column order
// follows the SELECT list order in the raw JSON, not alphabetical order.
// This matters because Go's encoding/json always alphabetizes map keys on
// marshal, which would silently reorder columns if we decoded rows
// straight into map[string]interface{} and used map iteration order.
func TestRESTClient_Query_PreservesColumnOrder(t *testing.T) {
	// Deliberately not alphabetical: Zebra, Apple, Middle.
	raw := `{"status":{"errors":[]},"result":{"content":[{"Zebra":1,"Apple":2,"Middle":3}]}}`
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(raw))
	}))
	defer srv.Close()

	c := NewRESTClient(testConfig(srv.URL))
	result, err := c.Query(context.Background(), "SELECT Zebra, Apple, Middle FROM T")
	if err != nil {
		t.Fatalf("Query returned error: %v", err)
	}
	got := []string{result.Columns[0].Name, result.Columns[1].Name, result.Columns[2].Name}
	want := []string{"Zebra", "Apple", "Middle"}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("column order = %v, want %v", got, want)
		}
	}
	if result.Rows[0][0] != float64(1) || result.Rows[0][1] != float64(2) || result.Rows[0][2] != float64(3) {
		t.Fatalf("row values misaligned with columns: %v", result.Rows[0])
	}
}

func TestRESTClient_NamespaceIsURLEscaped(t *testing.T) {
	// A namespace with characters that must survive path construction.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/atelier/v1/MY-NS/action/query" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(atelierQueryResponse{})
	}))
	defer srv.Close()

	cfg := testConfig(srv.URL)
	cfg.Namespace = "MY-NS"
	c := NewRESTClient(cfg)
	if _, err := c.Query(context.Background(), "SELECT 1"); err != nil {
		t.Fatalf("Query returned error: %v", err)
	}
}
