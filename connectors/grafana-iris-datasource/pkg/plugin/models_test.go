package plugin

import (
	"testing"
	"time"

	"github.com/grafana/grafana-plugin-sdk-go/backend"
)

func TestLoadPluginSettings_Defaults(t *testing.T) {
	settings := backend.DataSourceInstanceSettings{
		JSONData: []byte(`{"host":"iris.example.com","username":"grafana"}`),
		DecryptedSecureJSONData: map[string]string{
			"password": "s3cret",
		},
	}
	ps, err := LoadPluginSettings(settings)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if ps.WebPort != 52773 {
		t.Errorf("expected default webPort 52773, got %d", ps.WebPort)
	}
	if ps.Namespace != "USER" {
		t.Errorf("expected default namespace USER, got %q", ps.Namespace)
	}
	if ps.Password != "s3cret" {
		t.Errorf("expected password from secureJsonData, got %q", ps.Password)
	}
	if ps.Timeout != 30*time.Second {
		t.Errorf("expected default timeout 30s, got %v", ps.Timeout)
	}
	if got := ps.BaseURL(); got != "http://iris.example.com:52773" {
		t.Errorf("BaseURL() = %q", got)
	}
}

func TestLoadPluginSettings_ExplicitValues(t *testing.T) {
	settings := backend.DataSourceInstanceSettings{
		JSONData: []byte(`{"host":"iris.example.com","webPort":443,"namespace":"DEMO","username":"grafana","useHTTPS":true,"skipTLSVerify":true,"timeoutSeconds":5}`),
		DecryptedSecureJSONData: map[string]string{
			"password": "s3cret",
		},
	}
	ps, err := LoadPluginSettings(settings)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if ps.Namespace != "DEMO" || ps.WebPort != 443 || !ps.UseHTTPS || !ps.SkipTLSVerify {
		t.Fatalf("unexpected settings: %+v", ps)
	}
	if ps.Timeout != 5*time.Second {
		t.Errorf("expected timeout 5s, got %v", ps.Timeout)
	}
	if got := ps.BaseURL(); got != "https://iris.example.com:443" {
		t.Errorf("BaseURL() = %q", got)
	}
}

func TestLoadPluginSettings_MissingHost(t *testing.T) {
	settings := backend.DataSourceInstanceSettings{
		JSONData: []byte(`{"username":"grafana"}`),
	}
	if _, err := LoadPluginSettings(settings); err == nil {
		t.Fatal("expected an error for missing host, got nil")
	}
}

func TestLoadPluginSettings_NeverReadsPasswordFromPlainJSONData(t *testing.T) {
	// Regression guard for the CLAUDE.md/task requirement that the
	// password is only ever read from secureJsonData, never jsonData.
	settings := backend.DataSourceInstanceSettings{
		JSONData: []byte(`{"host":"iris.example.com","password":"leaked-plaintext"}`),
	}
	ps, err := LoadPluginSettings(settings)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if ps.Password != "" {
		t.Fatalf("password must never be sourced from plain jsonData, got %q", ps.Password)
	}
}
