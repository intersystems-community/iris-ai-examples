package plugin

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"github.com/grafana/grafana-plugin-sdk-go/backend"

	"github.com/intersystems-community/iris-ai-examples/connectors/grafana-iris-datasource/pkg/plugin/client"
)

// The plugin builds its HTTP client with the Grafana SDK's httpclient package, not net/http directly, so it
// inherits what Grafana adds to every data source: proxy settings, Private Data Source Connect (the secure
// SOCKS proxy that cloud users need to reach an on-premises IRIS), timeouts and request metrics.

func okServer(t *testing.T, tls bool, delay time.Duration) *httptest.Server {
	t.Helper()
	body, err := os.ReadFile("client/testdata/query_ok.json")
	if err != nil {
		t.Fatal(err)
	}
	h := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(delay)
		_, _ = w.Write(body)
	})
	if tls {
		return httptest.NewTLSServer(h)
	}
	return httptest.NewServer(h)
}

func clientFor(t *testing.T, url string, ps PluginSettings) *client.RESTClient {
	t.Helper()
	hc, err := newHTTPClient(context.Background(), backend.DataSourceInstanceSettings{}, &ps)
	if err != nil {
		t.Fatal(err)
	}
	return client.NewRESTClient(client.RESTClientConfig{BaseURL: url, Namespace: "USER", Username: "u", Password: "p", HTTPClient: hc})
}

func TestHTTPClient_ASelfSignedServerIsRefusedUnlessSkipVerifyIsOn(t *testing.T) {
	srv := okServer(t, true, 0)
	defer srv.Close()

	_, err := clientFor(t, srv.URL, PluginSettings{Timeout: 5 * time.Second}).Query(context.Background(), "SELECT 1")
	var unreachable *client.UnreachableError
	if !errors.As(err, &unreachable) {
		t.Fatalf("a certificate nobody trusts must fail, got %v", err)
	}

	if _, err := clientFor(t, srv.URL, PluginSettings{Timeout: 5 * time.Second, SkipTLSVerify: true}).Query(context.Background(), "SELECT 1"); err != nil {
		t.Fatalf("with skip verify on it should work: %v", err)
	}
}

func TestHTTPClient_TheConfiguredTimeoutIsHonoured(t *testing.T) {
	srv := okServer(t, false, 800*time.Millisecond)
	defer srv.Close()

	start := time.Now()
	_, err := clientFor(t, srv.URL, PluginSettings{Timeout: 150 * time.Millisecond}).Query(context.Background(), "SELECT 1")

	var unreachable *client.UnreachableError
	if !errors.As(err, &unreachable) {
		t.Fatalf("want a timeout reported as unreachable, got %v", err)
	}
	if took := time.Since(start); took > 600*time.Millisecond {
		t.Fatalf("the 150ms timeout was not applied: waited %s", took)
	}
}

func TestHTTPClient_AFastServerWithTheDefaultsWorks(t *testing.T) {
	srv := okServer(t, false, 0)
	defer srv.Close()

	if _, err := clientFor(t, srv.URL, PluginSettings{Timeout: 5 * time.Second}).Query(context.Background(), "SELECT 1"); err != nil {
		t.Fatal(err)
	}
}
