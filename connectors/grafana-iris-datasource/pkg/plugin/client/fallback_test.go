package client

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
)

// With no HTTPClient configured, NewRESTClient builds one itself. It must still honour the TLS setting.
func TestFallbackClient_HonoursInsecureSkipVerify(t *testing.T) {
	body, err := os.ReadFile("testdata/query_ok.json")
	if err != nil {
		t.Fatal(err)
	}
	srv := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { _, _ = w.Write(body) }))
	defer srv.Close()

	_, err = NewRESTClient(RESTClientConfig{BaseURL: srv.URL, Namespace: "USER"}).Query(context.Background(), "SELECT 1")
	var unreachable *UnreachableError
	if !errors.As(err, &unreachable) {
		t.Fatalf("an untrusted certificate must fail by default, got %v", err)
	}

	if _, err := NewRESTClient(RESTClientConfig{BaseURL: srv.URL, Namespace: "USER", InsecureSkipVerify: true}).Query(context.Background(), "SELECT 1"); err != nil {
		t.Fatalf("skip verify should allow it: %v", err)
	}
}
