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
}

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

	webPort := jd.WebPort
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
