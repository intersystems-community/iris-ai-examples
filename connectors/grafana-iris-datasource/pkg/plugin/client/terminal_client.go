package client

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/cookiejar"
	"strings"
	"sync"
	"time"

	"github.com/coder/websocket"
)

// TerminalClientConfig configures a TerminalClient.
type TerminalClientConfig struct {
	// BaseURL is the scheme+host+port of the IRIS web server, as for the REST client.
	BaseURL   string
	Namespace string
	Username  string
	Password  string
	// Timeout bounds one query, connection included; 0 means 30 seconds.
	Timeout time.Duration
	// HTTPClient carries Grafana's TLS, proxy and Private Data Source Connect settings. It is copied, given a
	// cookie jar and stripped of its Timeout, which would cut a WebSocket off; nil means a plain client.
	HTTPClient *http.Client
	// MaxResponseBytes caps the terminal output read for one query; 0 means DefaultMaxResponseBytes.
	MaxResponseBytes int64
	// MaxRows caps the rows read for one query; 0 means DefaultMaxRows.
	MaxRows int
	// Metrics scrapes /api/monitor/metrics; nil means metrics are unavailable on this connection.
	Metrics IRISClient
}

// TerminalClient is an IRISClient that runs each query through the Atelier terminal WebSocket
// (/api/atelier/v7/%SYS/terminal, IRIS 2023.2 and later), as the configured user, with SQL privilege checking
// on. It exists because /api/atelier/v1/{ns}/action/query prepares statements with privilege checking off:
// over REST a user granted SELECT on one view reads the base table and every other view as well. Here the
// same user gets SQLCODE -99. It needs nothing the REST path does not: /api/atelier already requires the
// %Development resource to log in at all.
//
// Each query is one short WebSocket session: the client types a fixed program and the SQL as base64 (see
// terminal_protocol.go), reads the result, and hangs up. One CSP session cookie is shared by every
// connection, because a connection without one holds a licence slot until its session times out.
type TerminalClient struct {
	cfg TerminalClientConfig
	hc  *http.Client
	now func() time.Time

	mu     sync.Mutex
	seeded time.Time
}

var _ IRISClient = (*TerminalClient)(nil)

// sessionRefresh renews the CSP session well inside IRIS's default 900-second timeout.
const sessionRefresh = 5 * time.Minute

// NewTerminalClient makes no network calls; the first query does.
func NewTerminalClient(cfg TerminalClientConfig) *TerminalClient {
	hc := &http.Client{}
	if cfg.HTTPClient != nil {
		copied := *cfg.HTTPClient
		hc = &copied
	}
	hc.Timeout = 0
	hc.Jar, _ = cookiejar.New(nil) // cookiejar.New never fails with nil options
	return &TerminalClient{cfg: cfg, hc: hc, now: time.Now}
}

func (c *TerminalClient) base() string { return strings.TrimRight(c.cfg.BaseURL, "/") }

func (c *TerminalClient) authHeader() string {
	return "Basic " + base64.StdEncoding.EncodeToString([]byte(c.cfg.Username+":"+c.cfg.Password))
}

// Query implements IRISClient.
func (c *TerminalClient) Query(ctx context.Context, sql string) (*QueryResult, error) {
	timeout := c.cfg.Timeout
	if timeout <= 0 {
		timeout = 30 * time.Second
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	res, err := c.queryOnce(ctx, sql)
	var hungUp *hungUpError
	if errors.As(err, &hungUp) {
		// IRIS closes the socket before init when the session cookie is dead; start a new session, once.
		c.forgetSession()
		res, err = c.queryOnce(ctx, sql)
		if errors.As(err, &hungUp) {
			err = &UnreachableError{Err: errors.New("the IRIS terminal closed the connection before it started")}
		}
	}
	if err != nil && ctx.Err() != nil {
		return nil, &UnreachableError{Err: ctx.Err()}
	}
	return res, err
}

// hungUpError is the terminal closing the socket before its init frame.
type hungUpError struct{ err error }

func (e *hungUpError) Error() string { return "iris: the terminal hung up: " + e.err.Error() }

func (c *TerminalClient) queryOnce(ctx context.Context, sql string) (*QueryResult, error) {
	if err := c.ensureSession(ctx); err != nil {
		return nil, err
	}
	conn, err := c.dial(ctx)
	if err != nil {
		return nil, err
	}
	defer conn.CloseNow()
	maxBytes := c.cfg.MaxResponseBytes
	if maxBytes <= 0 {
		maxBytes = DefaultMaxResponseBytes
	}
	conn.SetReadLimit(maxBytes + 4096)

	t := &terminalSession{conn: conn}
	if err := t.start(ctx, c.cfg.Namespace); err != nil {
		return nil, err
	}
	lines := terminalLines(sql)
	for _, line := range lines[:len(lines)-1] {
		if err := t.run(ctx, line, nil); err != nil {
			return nil, err
		}
	}
	maxRows := c.cfg.MaxRows
	if maxRows <= 0 {
		maxRows = DefaultMaxRows
	}
	out := newTerminalOutput(int(maxBytes), maxRows)
	if err := t.run(ctx, lines[len(lines)-1], out); err != nil {
		_ = t.send(ctx, map[string]any{"type": "interrupt"})
		return nil, err
	}
	if !out.done {
		return nil, fmt.Errorf("iris: the terminal returned no result: %q", out.strayText())
	}
	_ = conn.Close(websocket.StatusNormalClosure, "")
	return out.result()
}

// ensureSession makes sure the cookie jar holds a live CSP session, and checks the credentials doing it.
func (c *TerminalClient) ensureSession(ctx context.Context) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	if !c.seeded.IsZero() && c.now().Sub(c.seeded) < sessionRefresh {
		return nil
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.base()+"/api/atelier/", nil)
	if err != nil {
		return fmt.Errorf("iris: building request: %w", err)
	}
	req.Header.Set("Authorization", c.authHeader())
	resp, err := c.hc.Do(req)
	if err != nil {
		return &UnreachableError{Err: err}
	}
	resp.Body.Close()
	switch {
	case resp.StatusCode == http.StatusUnauthorized || resp.StatusCode == http.StatusForbidden:
		return &AuthError{HTTPStatus: resp.StatusCode}
	case resp.StatusCode != http.StatusOK:
		return fmt.Errorf("iris: unexpected HTTP status %d from /api/atelier/", resp.StatusCode)
	}
	c.seeded = c.now()
	return nil
}

func (c *TerminalClient) forgetSession() {
	c.mu.Lock()
	c.seeded = time.Time{}
	c.mu.Unlock()
}

func (c *TerminalClient) dial(ctx context.Context) (*websocket.Conn, error) {
	url := c.base() + "/api/atelier/v7/%25SYS/terminal"
	h := http.Header{}
	h.Set("Authorization", c.authHeader())
	conn, resp, err := websocket.Dial(ctx, url, &websocket.DialOptions{HTTPClient: c.hc, HTTPHeader: h})
	if err == nil {
		return conn, nil
	}
	if resp != nil {
		switch resp.StatusCode {
		case http.StatusUnauthorized, http.StatusForbidden:
			return nil, &AuthError{HTTPStatus: resp.StatusCode}
		case http.StatusNotFound:
			return nil, &ConfigError{Message: "this IRIS has no web terminal (/api/atelier/v7/%SYS/terminal needs IRIS 2023.2 or later); use the REST connection"}
		}
	}
	return nil, &UnreachableError{Err: err}
}

// terminalSession is one connection's conversation: init, config, then a prompt after every line.
type terminalSession struct{ conn *websocket.Conn }

type terminalFrame struct {
	Type string `json:"type"`
	Text string `json:"text"`
	NS   string `json:"ns"`
}

func (t *terminalSession) send(ctx context.Context, v map[string]any) error {
	b, _ := json.Marshal(v)
	if err := t.conn.Write(ctx, websocket.MessageText, b); err != nil {
		return &UnreachableError{Err: err}
	}
	return nil
}

func (t *terminalSession) next(ctx context.Context) (terminalFrame, error) {
	var f terminalFrame
	_, b, err := t.conn.Read(ctx)
	if err != nil {
		return f, &UnreachableError{Err: err}
	}
	if err := json.Unmarshal(b, &f); err != nil {
		return f, fmt.Errorf("iris: unreadable terminal frame: %w", err)
	}
	return f, nil
}

// start waits for init, switches to the namespace and waits for its prompt.
func (t *terminalSession) start(ctx context.Context, namespace string) error {
	f, err := t.next(ctx)
	if err != nil {
		if ctx.Err() == nil {
			return &hungUpError{err: err}
		}
		return err
	}
	if f.Type != "init" {
		return fmt.Errorf("iris: the terminal began with %q, not init", f.Type)
	}
	if err := t.send(ctx, map[string]any{"type": "config", "namespace": namespace, "rawMode": false}); err != nil {
		return err
	}
	f, err = t.next(ctx)
	if err != nil {
		return err
	}
	switch {
	case f.Type == "error" && strings.Contains(f.Text, "<NAMESPACE>"):
		return &ConfigError{Message: fmt.Sprintf("namespace %q does not exist, or this user cannot use it", namespace)}
	case f.Type == "error":
		return fmt.Errorf("iris: the terminal refused the session: %s", f.Text)
	case f.Type != "prompt" || !strings.EqualFold(f.NS, namespace):
		return fmt.Errorf("iris: the terminal did not switch to namespace %q (got %s %q)", namespace, f.Type, f.NS)
	}
	return nil
}

// run types one line and reads up to the next prompt, feeding any output to out (discarding it if nil). It
// returns as soon as out has its result.
func (t *terminalSession) run(ctx context.Context, line string, out *terminalOutput) error {
	if err := t.send(ctx, map[string]any{"type": "prompt", "input": line}); err != nil {
		return err
	}
	for {
		f, err := t.next(ctx)
		if err != nil {
			return err
		}
		switch f.Type {
		case "prompt":
			return nil
		case "error":
			return fmt.Errorf("iris: the terminal reported an error: %s", f.Text)
		case "output":
			if out == nil {
				continue
			}
			if err := out.feed(f.Text); err != nil {
				return err
			}
			if out.done {
				return nil
			}
		}
	}
}

// Ping checks the credentials and that the terminal runs SQL for this user.
func (c *TerminalClient) Ping(ctx context.Context) error {
	_, err := c.Query(ctx, "SELECT 1")
	return err
}

// Metrics scrapes through the web-port client.
func (c *TerminalClient) Metrics(ctx context.Context) ([]MetricSample, error) {
	if c.cfg.Metrics == nil {
		return nil, &ConfigError{Message: "SAM metrics are not available on this connection"}
	}
	return c.cfg.Metrics.Metrics(ctx)
}
