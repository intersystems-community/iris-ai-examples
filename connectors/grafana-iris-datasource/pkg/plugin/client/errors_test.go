package client

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestErrors_ASQLErrorFromIRISIsATypedSQLError(t *testing.T) {
	c := serveFixture(t, "query_error.json")

	_, err := c.Query(context.Background(), "SELECT * FROM No.Such")

	var sqlErr *SQLError
	if !errors.As(err, &sqlErr) {
		t.Fatalf("want *SQLError, got %T: %v", err, err)
	}
	if sqlErr.Code != 5540 || !strings.Contains(sqlErr.Message, "IDENTIFIER expected") {
		t.Fatalf("unexpected: %+v", sqlErr)
	}
}

func TestErrors_Authentication(t *testing.T) {
	for _, status := range []int{http.StatusUnauthorized, http.StatusForbidden} {
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(status) }))
		c := NewRESTClient(RESTClientConfig{BaseURL: srv.URL, Namespace: "USER"})

		_, err := c.Query(context.Background(), "SELECT 1")
		srv.Close()

		var authErr *AuthError
		if !errors.As(err, &authErr) || authErr.HTTPStatus != status {
			t.Fatalf("HTTP %d: want *AuthError, got %T: %v", status, err, err)
		}
		if !strings.Contains(err.Error(), "authentication failed") {
			t.Fatalf("message changed: %v", err)
		}
	}
}

func TestErrors_AnUnreachableServerIsATypedError(t *testing.T) {
	srv := httptest.NewServer(http.NotFoundHandler())
	url := srv.URL
	srv.Close() // nothing listens there now
	c := NewRESTClient(RESTClientConfig{BaseURL: url, Namespace: "USER"})

	_, err := c.Query(context.Background(), "SELECT 1")

	var un *UnreachableError
	if !errors.As(err, &un) {
		t.Fatalf("want *UnreachableError, got %T: %v", err, err)
	}
}

func TestErrors_AnOversizedResponseIsRefusedNotBuffered(t *testing.T) {
	big := strings.Repeat("x", 4096)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"status":{"errors":[]},"result":{"content":[{"a":"` + big + `"}]}}`))
	}))
	defer srv.Close()
	c := NewRESTClient(RESTClientConfig{BaseURL: srv.URL, Namespace: "USER", MaxResponseBytes: 1024})

	_, err := c.Query(context.Background(), "SELECT a FROM T")

	var tooBig *TooLargeError
	if !errors.As(err, &tooBig) || tooBig.Limit != 1024 {
		t.Fatalf("want *TooLargeError with the limit, got %T: %v", err, err)
	}
	if !strings.Contains(err.Error(), "TOP") {
		t.Fatalf("the message should tell the user how to fix it: %v", err)
	}
}

func TestErrors_TheDefaultLimitIsGenerousButFinite(t *testing.T) {
	if DefaultMaxResponseBytes < 8<<20 || DefaultMaxResponseBytes > 512<<20 {
		t.Fatalf("default %d is not a sane order of magnitude", DefaultMaxResponseBytes)
	}
}
