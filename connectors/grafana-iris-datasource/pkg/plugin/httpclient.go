package plugin

import (
	"context"
	"net/http"

	"github.com/grafana/grafana-plugin-sdk-go/backend"
	"github.com/grafana/grafana-plugin-sdk-go/backend/httpclient"
)

// newHTTPClient builds the client used to talk to IRIS with the SDK's httpclient package. Beyond plain
// net/http this gives the data source Grafana's proxy settings, the secure SOCKS proxy (Private Data Source
// Connect, which cloud users need to reach an on-premises IRIS when the data source enables it), request
// metrics and tracing.
func newHTTPClient(ctx context.Context, settings backend.DataSourceInstanceSettings, ps *PluginSettings) (*http.Client, error) {
	opts, err := settings.HTTPClientOptions(ctx)
	if err != nil {
		return nil, err
	}
	if opts.Timeouts == nil {
		timeouts := httpclient.DefaultTimeoutOptions
		opts.Timeouts = &timeouts
	}
	if ps.Timeout > 0 {
		opts.Timeouts.Timeout = ps.Timeout
	}
	if ps.SkipTLSVerify {
		if opts.TLS == nil {
			opts.TLS = &httpclient.TLSOptions{}
		}
		opts.TLS.InsecureSkipVerify = true
	}
	return httpclient.New(opts)
}
