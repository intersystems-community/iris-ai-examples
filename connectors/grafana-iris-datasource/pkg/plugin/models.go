package plugin

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/grafana/grafana-plugin-sdk-go/backend"
)

// jsonData is the shape of the non-secret configuration stored by
// Grafana's config editor in DataSourceInstanceSettings.JSONData. It must
// never contain the password: that belongs only in secureJsonData, which
// Grafana encrypts at rest and which shows up here already decrypted in
// DecryptedSecureJSONData.
type jsonData struct {
	Host           string `json:"host"`
	WebPort        int    `json:"webPort"`
	Namespace      string `json:"namespace"`
	Username       string `json:"username"`
	UseHTTPS       bool   `json:"useHTTPS"`
	SkipTLSVerify  bool   `json:"skipTLSVerify"`
	TimeoutSeconds int    `json:"timeoutSeconds"`
	// AllowWrites lifts the read-only guard (readonly.go). Off unless set.
	AllowWrites bool `json:"allowWrites"`
	// Transport is how the plugin talks to IRIS: "rest" (default, the web port) or "native" (the SuperServer).
	Transport string `json:"transport"`
	// SuperServerPort is the SuperServer port used by the native transport. Defaults to 1972.
	SuperServerPort int `json:"superserverPort"`
	// Connection pool for the native transport.
	MaxOpenConns           int `json:"maxOpenConns"`
	MaxIdleConns           int `json:"maxIdleConns"`
	ConnMaxLifetimeSeconds int `json:"connMaxLifetimeSeconds"`
	// RowLimit caps the rows one query returns; 0 (the default) means no cap. A query's own rowLimit overrides it.
	RowLimit int `json:"rowLimit"`
}

// PluginSettings is the parsed, validated configuration for one instance
// of the IRIS datasource.
type PluginSettings struct {
	Host          string
	WebPort       int
	Namespace     string
	Username      string
	Password      string
	UseHTTPS      bool
	SkipTLSVerify bool
	Timeout       time.Duration
	AllowWrites   bool
	RowLimit      int

	// Transport is TransportREST or TransportNative.
	Transport       string
	SuperServerPort int
	// WebPortSet is true when the user gave a web port. The native transport scrapes SAM metrics through the
	// web port, so it offers them only then; the REST transport needs the port anyway and defaults it.
	WebPortSet      bool
	MaxOpenConns    int
	MaxIdleConns    int
	ConnMaxLifetime time.Duration
}

// The transports a data source can use.
const (
	TransportREST   = "rest"
	TransportNative = "native"
)

// LoadPluginSettings parses a data source instance's JSONData and
// DecryptedSecureJSONData into a PluginSettings, applying defaults and
// validating the fields the REST client needs.
func LoadPluginSettings(settings backend.DataSourceInstanceSettings) (*PluginSettings, error) {
	var jd jsonData
	if len(settings.JSONData) > 0 {
		if err := json.Unmarshal(settings.JSONData, &jd); err != nil {
			return nil, fmt.Errorf("iris: invalid jsonData: %w", err)
		}
	}

	host := strings.TrimSpace(jd.Host)
	if host == "" {
		return nil, fmt.Errorf("iris: host is required")
	}

	namespace := strings.TrimSpace(jd.Namespace)
	if namespace == "" {
		namespace = "USER"
	}

	transport := strings.TrimSpace(jd.Transport)
	if transport == "" {
		transport = TransportREST
	}
	if transport != TransportREST && transport != TransportNative {
		return nil, fmt.Errorf("iris: unknown transport %q (use %q or %q)", transport, TransportREST, TransportNative)
	}

	webPort := jd.WebPort
	webPortSet := webPort != 0
	if webPort == 0 {
		webPort = 52773
	}

	timeoutSeconds := jd.TimeoutSeconds
	if timeoutSeconds <= 0 {
		timeoutSeconds = 30
	}

	password := ""
	if settings.DecryptedSecureJSONData != nil {
		password = settings.DecryptedSecureJSONData["password"]
	}

	return &PluginSettings{
		Host:          host,
		WebPort:       webPort,
		Namespace:     namespace,
		Username:      jd.Username,
		Password:      password,
		UseHTTPS:      jd.UseHTTPS,
		SkipTLSVerify: jd.SkipTLSVerify,
		Timeout:       time.Duration(timeoutSeconds) * time.Second,
		AllowWrites:   jd.AllowWrites,
		RowLimit:      max(jd.RowLimit, 0),

		Transport:       transport,
		SuperServerPort: orDefault(jd.SuperServerPort, 1972),
		WebPortSet:      webPortSet,
		MaxOpenConns:    orDefault(jd.MaxOpenConns, 10),
		MaxIdleConns:    orDefault(jd.MaxIdleConns, 5),
		ConnMaxLifetime: time.Duration(orDefault(jd.ConnMaxLifetimeSeconds, 1800)) * time.Second,
	}, nil
}

// BaseURL builds the IRIS web server base URL (scheme://host:port) from
// these settings.
func (s *PluginSettings) BaseURL() string {
	scheme := "http"
	if s.UseHTTPS {
		scheme = "https"
	}
	return fmt.Sprintf("%s://%s:%d", scheme, s.Host, s.WebPort)
}

// orDefault is v, or def when v is unset or not positive.
func orDefault(v, def int) int {
	if v <= 0 {
		return def
	}
	return v
}
