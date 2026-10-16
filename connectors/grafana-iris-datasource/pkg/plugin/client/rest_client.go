package client

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

// RESTClientConfig configures a RESTClient.
type RESTClientConfig struct {
	// BaseURL is the scheme+host+port of the IRIS web server, e.g.
	// "https://iris.example.com:52773". No trailing slash.
	BaseURL string
	// Namespace is the IRIS namespace to run queries against, e.g. "USER".
	Namespace string
	Username  string
	Password  string
	// InsecureSkipVerify disables TLS certificate verification. Only ever
	// set this for self-signed lab/demo instances.
	InsecureSkipVerify bool
	Timeout            time.Duration
}

// RESTClient is the production IRISClient implementation. It talks to IRIS
// entirely over HTTP using two documented, stock endpoints:
//
//   - POST /api/atelier/v1/{namespace}/action/query — runs one SQL
//     statement and returns rows as an array of JSON objects keyed by
//     column name. This is the %Api.Atelier "action/query" call; see
//     https://docs.intersystems.com and the community posts cited in
//     README.md for the request/response shape used here.
//   - GET /api/monitor/metrics — IRIS's built-in SAM/Prometheus metrics
//     endpoint, OpenMetrics text exposition format.
//
// Both are enabled on a stock IRIS install's web (superserver-adjacent)
// port, by default 52773, and both are reachable with nothing more than
// net/http and encoding/json — no cgo, no bundled JDBC/JVM, no sidecar
// process. See client.go's package doc for why this was chosen over the
// pgwire and JDBC-bridge alternatives.
type RESTClient struct {
	cfg        RESTClientConfig
	httpClient *http.Client
}

// NewRESTClient builds a RESTClient from cfg. It does not make any network
// calls; use Ping to verify connectivity.
func NewRESTClient(cfg RESTClientConfig) *RESTClient {
	timeout := cfg.Timeout
	if timeout <= 0 {
		timeout = 30 * time.Second
	}
	return &RESTClient{
		cfg: cfg,
		httpClient: &http.Client{
			Timeout: timeout,
		},
	}
}

type atelierQueryRequest struct {
	Query      string        `json:"query"`
	Parameters []interface{} `json:"parameters"`
}

type atelierStatus struct {
	Errors  []string `json:"errors"`
	Summary string   `json:"summary"`
}

type atelierQueryResult struct {
	Status atelierStatus `json:"status"`
	Result struct {
		Content []map[string]interface{} `json:"content"`
	} `json:"result"`
}

// queryURL builds the Atelier action/query URL for the configured
// namespace, URL-escaping it so namespaces with unusual characters still
// produce a valid path.
func (c *RESTClient) queryURL() string {
	return fmt.Sprintf("%s/api/atelier/v1/%s/action/query", strings.TrimRight(c.cfg.BaseURL, "/"), url.PathEscape(c.cfg.Namespace))
}

func (c *RESTClient) metricsURL() string {
	return strings.TrimRight(c.cfg.BaseURL, "/") + "/api/monitor/metrics"
}

// Query implements IRISClient.
func (c *RESTClient) Query(ctx context.Context, sql string) (*QueryResult, error) {
	reqBody, err := json.Marshal(atelierQueryRequest{Query: sql, Parameters: []interface{}{}})
	if err != nil {
		return nil, fmt.Errorf("iris: encoding query request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.queryURL(), bytes.NewReader(reqBody))
	if err != nil {
		return nil, fmt.Errorf("iris: building request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.SetBasicAuth(c.cfg.Username, c.cfg.Password)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("iris: query request failed: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("iris: reading response: %w", err)
	}

	if resp.StatusCode == http.StatusUnauthorized || resp.StatusCode == http.StatusForbidden {
		return nil, fmt.Errorf("iris: authentication failed (HTTP %d)", resp.StatusCode)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("iris: unexpected HTTP status %d: %s", resp.StatusCode, string(body))
	}

	var parsed atelierQueryResult
	if err := json.Unmarshal(body, &parsed); err != nil {
		return nil, fmt.Errorf("iris: decoding query response: %w", err)
	}
	if len(parsed.Status.Errors) > 0 {
		return nil, fmt.Errorf("iris: query failed: %s", strings.Join(parsed.Status.Errors, "; "))
	}

	return contentToQueryResult(body, parsed.Result.Content)
}

// contentToQueryResult converts the decoded "content" rows into a
// QueryResult, deriving column order from the first row's key order in
// the *raw* JSON (map iteration order in Go is not stable, so we re-walk
// the raw bytes with json.Decoder to recover it) and falling back to a
// sorted column list if that walk fails for any reason.
func contentToQueryResult(raw []byte, content []map[string]interface{}) (*QueryResult, error) {
	if len(content) == 0 {
		return &QueryResult{Columns: nil, Rows: nil}, nil
	}

	columnOrder, err := firstRowKeyOrder(raw)
	if err != nil || len(columnOrder) != len(content[0]) {
		columnOrder = sortedKeys(content[0])
	}

	columns := make([]Column, len(columnOrder))
	for i, name := range columnOrder {
		columns[i] = Column{Name: name}
	}

	rows := make([]Row, len(content))
	for i, rowMap := range content {
		row := make(Row, len(columnOrder))
		for j, name := range columnOrder {
			row[j] = rowMap[name]
		}
		rows[i] = row
	}

	return &QueryResult{Columns: columns, Rows: rows}, nil
}

func sortedKeys(m map[string]interface{}) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	for i := 1; i < len(keys); i++ {
		for j := i; j > 0 && keys[j-1] > keys[j]; j-- {
			keys[j-1], keys[j] = keys[j], keys[j-1]
		}
	}
	return keys
}

// firstRowKeyOrder walks the raw response bytes with a streaming decoder
// to find the key order of result.content[0], since decoding into
// map[string]interface{} discards it. It only ever needs to walk down
// through the top-level object's "result" key, that object's "content"
// key, and the first element of that array.
func firstRowKeyOrder(raw []byte) ([]string, error) {
	dec := json.NewDecoder(bytes.NewReader(raw))
	if err := expectDelim(dec, '{'); err != nil {
		return nil, err
	}
	if err := seekKey(dec, "result"); err != nil {
		return nil, err
	}
	if err := expectDelim(dec, '{'); err != nil {
		return nil, err
	}
	if err := seekKey(dec, "content"); err != nil {
		return nil, err
	}
	if err := expectDelim(dec, '['); err != nil {
		return nil, err
	}
	if !dec.More() {
		return nil, fmt.Errorf("iris: content array is empty")
	}
	if err := expectDelim(dec, '{'); err != nil {
		return nil, err
	}
	return decodeObjectKeyOrder(dec)
}

// expectDelim reads the next token from dec and requires it to be the
// given JSON delimiter.
func expectDelim(dec *json.Decoder, want json.Delim) error {
	tok, err := dec.Token()
	if err != nil {
		return err
	}
	delim, ok := tok.(json.Delim)
	if !ok || delim != want {
		return fmt.Errorf("iris: expected delimiter %q, got %v", want, tok)
	}
	return nil
}

// seekKey reads key/value pairs from an already-opened JSON object until
// it finds a key equal to target, leaving the decoder positioned right
// before that key's value. Every other key's value is skipped over
// whole. Returns an error if target is never found before the object
// closes.
func seekKey(dec *json.Decoder, target string) error {
	for dec.More() {
		tok, err := dec.Token()
		if err != nil {
			return err
		}
		key, ok := tok.(string)
		if !ok {
			return fmt.Errorf("iris: expected object key, got %v", tok)
		}
		if key == target {
			return nil
		}
		if err := skipValue(dec); err != nil {
			return err
		}
	}
	return fmt.Errorf("iris: key %q not found", target)
}

// decodeObjectKeyOrder reads key/value token pairs from an already-opened
// JSON object (the '{' has been consumed) and returns the keys in the
// order they appear, skipping over their values regardless of shape.
func decodeObjectKeyOrder(dec *json.Decoder) ([]string, error) {
	var keys []string
	for dec.More() {
		tok, err := dec.Token()
		if err != nil {
			return nil, err
		}
		key, ok := tok.(string)
		if !ok {
			return nil, fmt.Errorf("expected object key, got %v", tok)
		}
		keys = append(keys, key)
		if err := skipValue(dec); err != nil {
			return nil, err
		}
	}
	// consume closing '}'
	if _, err := dec.Token(); err != nil {
		return nil, err
	}
	return keys, nil
}

// skipValue consumes one JSON value (scalar, object, or array) from dec.
func skipValue(dec *json.Decoder) error {
	tok, err := dec.Token()
	if err != nil {
		return err
	}
	delim, ok := tok.(json.Delim)
	if !ok {
		return nil // scalar already consumed
	}
	depth := 1
	for depth > 0 {
		t, err := dec.Token()
		if err != nil {
			return err
		}
		if d, ok := t.(json.Delim); ok {
			switch d {
			case '{', '[':
				depth++
			case '}', ']':
				depth--
			}
		}
	}
	_ = delim
	return nil
}

// Ping implements IRISClient by running a trivial query. A REST-reachable,
// authenticated IRIS instance that can execute SQL is exactly what the
// query editor needs, so this doubles as a meaningful health check.
func (c *RESTClient) Ping(ctx context.Context) error {
	_, err := c.Query(ctx, "SELECT 1")
	return err
}

// Metrics implements IRISClient by scraping /api/monitor/metrics and
// parsing the OpenMetrics/Prometheus text exposition format.
func (c *RESTClient) Metrics(ctx context.Context) ([]MetricSample, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.metricsURL(), nil)
	if err != nil {
		return nil, fmt.Errorf("iris: building metrics request: %w", err)
	}
	req.SetBasicAuth(c.cfg.Username, c.cfg.Password)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("iris: metrics request failed: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("iris: reading metrics response: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("iris: unexpected HTTP status %d from metrics endpoint: %s", resp.StatusCode, string(body))
	}

	return parseOpenMetrics(body)
}

// parseOpenMetrics is a minimal, dependency-free parser for the
// OpenMetrics/Prometheus text exposition format, which is what
// /api/monitor/metrics returns. It intentionally supports only what that
// endpoint emits: optional "# HELP"/"# TYPE" comment lines, then lines of
// the form `metric_name{label="value",...} number` or `metric_name number`.
func parseOpenMetrics(body []byte) ([]MetricSample, error) {
	var samples []MetricSample
	for _, line := range strings.Split(string(body), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		name := line
		labels := map[string]string{}
		rest := line

		if idx := strings.IndexByte(line, '{'); idx >= 0 {
			end := strings.IndexByte(line[idx:], '}')
			if end < 0 {
				continue // malformed line; skip rather than fail the whole scrape
			}
			end += idx
			name = line[:idx]
			labelBody := line[idx+1 : end]
			for _, pair := range splitLabelPairs(labelBody) {
				k, v, ok := parseLabelPair(pair)
				if ok {
					labels[k] = v
				}
			}
			rest = strings.TrimSpace(line[end+1:])
		} else {
			fields := strings.Fields(line)
			if len(fields) < 2 {
				continue
			}
			name = fields[0]
			rest = fields[1]
		}

		valueField := strings.Fields(rest)
		if len(valueField) == 0 {
			continue
		}
		value, err := strconv.ParseFloat(valueField[0], 64)
		if err != nil {
			continue // not a numeric sample line; skip
		}

		samples = append(samples, MetricSample{
			Name:   strings.TrimSpace(name),
			Labels: labels,
			Value:  value,
		})
	}
	return samples, nil
}

// splitLabelPairs splits a `k="v",k2="v2"` label body on commas that are
// outside of quoted values.
func splitLabelPairs(body string) []string {
	var pairs []string
	var cur strings.Builder
	inQuotes := false
	for i := 0; i < len(body); i++ {
		ch := body[i]
		switch {
		case ch == '"' && (i == 0 || body[i-1] != '\\'):
			inQuotes = !inQuotes
			cur.WriteByte(ch)
		case ch == ',' && !inQuotes:
			pairs = append(pairs, cur.String())
			cur.Reset()
		default:
			cur.WriteByte(ch)
		}
	}
	if cur.Len() > 0 {
		pairs = append(pairs, cur.String())
	}
	return pairs
}

func parseLabelPair(pair string) (key, value string, ok bool) {
	pair = strings.TrimSpace(pair)
	idx := strings.IndexByte(pair, '=')
	if idx < 0 {
		return "", "", false
	}
	key = strings.TrimSpace(pair[:idx])
	value = strings.TrimSpace(pair[idx+1:])
	value = strings.Trim(value, `"`)
	return key, value, key != ""
}
