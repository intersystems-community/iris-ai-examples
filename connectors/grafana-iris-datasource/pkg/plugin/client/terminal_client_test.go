package client

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/coder/websocket"
)

// fakeTerminal behaves like the Atelier terminal as measured on IRIS 2026.1: Basic auth on GET /api/atelier/
// sets the CSP session cookie, the WebSocket upgrade sets none, a bad namespace is an "error" frame, a line
// of 427 characters or more is dropped without output, and output arrives in pieces.
type fakeTerminal struct {
	t *testing.T
	// answer is what the terminal prints for the SQL a query carries.
	answer func(sql string) string
	// namespaces the user may switch to.
	namespaces map[string]bool
	// closeFirst closes the first n WebSocket sessions before init, as IRIS does for a dead session.
	closeFirst int
	// noTerminal answers the WebSocket path with 404, as IRIS before 2023.2 does.
	noTerminal bool
	// hang never answers the Xecute line.
	hang bool

	mu       sync.Mutex
	gets     int
	sessions int
	cookies  []string
	lines    []string
}

func (f *fakeTerminal) server() *httptest.Server {
	mux := http.NewServeMux()
	mux.HandleFunc("/api/atelier/", func(w http.ResponseWriter, r *http.Request) {
		if u, p, _ := r.BasicAuth(); u != "acme" || p != "pw" {
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}
		if r.URL.Path == "/api/atelier/v7/%SYS/terminal" {
			f.terminal(w, r)
			return
		}
		f.mu.Lock()
		f.gets++
		f.mu.Unlock()
		http.SetCookie(w, &http.Cookie{Name: "CSPSESSIONID-SP-1-UP-api-atelier-", Value: "s1", Path: "/api/atelier/"})
		_, _ = w.Write([]byte(`{"status":{"errors":[]},"result":{"content":{"version":"IRIS 2026.1"}}}`))
	})
	srv := httptest.NewServer(mux)
	f.t.Cleanup(srv.Close)
	return srv
}

func (f *fakeTerminal) terminal(w http.ResponseWriter, r *http.Request) {
	if f.noTerminal {
		http.NotFound(w, r)
		return
	}
	f.mu.Lock()
	f.sessions++
	n := f.sessions
	f.cookies = append(f.cookies, r.Header.Get("Cookie"))
	f.mu.Unlock()
	c, err := websocket.Accept(w, r, nil)
	if err != nil {
		return
	}
	defer c.CloseNow()
	ctx := r.Context()
	if n <= f.closeFirst {
		return
	}
	send := func(v map[string]any) { b, _ := json.Marshal(v); _ = c.Write(ctx, websocket.MessageText, b) }
	read := func() map[string]any {
		_, b, err := c.Read(ctx)
		if err != nil {
			return nil
		}
		var m map[string]any
		_ = json.Unmarshal(b, &m)
		return m
	}
	send(map[string]any{"type": "init", "protocol": 1, "version": "IRIS 2026.1"})
	cfg := read()
	ns, _ := cfg["namespace"].(string)
	if !f.namespaces[ns] {
		send(map[string]any{"type": "error", "text": "ERROR #5002: ObjectScript error: <NAMESPACE>Server+28^%Atelier.v7.TerminalAgent.1"})
		return
	}
	prompt := func() { send(map[string]any{"type": "prompt", "text": "\x1b[1m" + ns + ">\x1b[0m", "ns": ns}) }
	prompt()
	vars := map[string]string{}
	for {
		m := read()
		if m == nil || m["type"] != "prompt" {
			return
		}
		line, _ := m["input"].(string)
		f.mu.Lock()
		f.lines = append(f.lines, line)
		f.mu.Unlock()
		switch {
		case len(line) >= 427:
			// dropped without a word
		case line == `Kill  Set tP="",tS=""`:
			vars = map[string]string{"tP": "", "tS": ""}
		case strings.HasPrefix(line, "Set "):
			name, rest, _ := strings.Cut(strings.TrimPrefix(line, "Set "), "=")
			vars[name] += strings.TrimSuffix(strings.TrimPrefix(rest, name+`_"`), `"`)
		case strings.HasPrefix(line, "Xecute "):
			if f.hang {
				<-ctx.Done()
				return
			}
			program, _ := base64.StdEncoding.DecodeString(vars["tP"])
			if string(program) != terminalProgram {
				send(map[string]any{"type": "output", "text": "<SYNTAX>"})
				break
			}
			sql, _ := base64.StdEncoding.DecodeString(vars["tS"])
			out := f.answer(string(sql))
			for len(out) > 0 { // in pieces, as the terminal sends it
				k := min(37, len(out))
				send(map[string]any{"type": "output", "text": out[:k]})
				out = out[k:]
			}
		}
		prompt()
	}
}

func rowsOutput(cols string, rows ...string) string {
	out := "~IGD-COLS~" + b64(cols) + "~IGD-END~"
	for _, r := range rows {
		out += "~IGD-ROW~" + b64(r) + "~IGD-END~"
	}
	return out + "~IGD-OK~\r\n\x1b[31;1m<EDITED>\x1b[0m"
}

func newFake(t *testing.T) *fakeTerminal {
	return &fakeTerminal{t: t, namespaces: map[string]bool{"USER": true}, answer: func(sql string) string {
		return rowsOutput(`[{"name":"TenantID","type":10},{"name":"v","type":5}]`, `["acme",1]`)
	}}
}

func terminalFor(srv *httptest.Server, mutate ...func(*TerminalClientConfig)) *TerminalClient {
	cfg := TerminalClientConfig{BaseURL: srv.URL, Namespace: "USER", Username: "acme", Password: "pw", Timeout: 5 * time.Second}
	for _, m := range mutate {
		m(&cfg)
	}
	return NewTerminalClient(cfg)
}

func TestTerminalClient_RunsTheQueryAndReturnsTypedRows(t *testing.T) {
	f := newFake(t)
	var got string
	f.answer = func(sql string) string {
		got = sql
		return rowsOutput(`[{"name":"TenantID","type":10},{"name":"v","type":5}]`, `["acme",1]`, `[null,2]`)
	}
	res, err := terminalFor(f.server()).Query(context.Background(), "SELECT TenantID, v FROM Acme_Events")
	if err != nil {
		t.Fatal(err)
	}
	if got != "SELECT TenantID, v FROM Acme_Events" {
		t.Fatalf("the terminal ran %q", got)
	}
	if len(res.Columns) != 2 || res.Columns[0].Name != "TenantID" || len(res.Rows) != 2 || res.Rows[0][1] != 1.0 || res.Rows[1][0] != nil {
		t.Fatalf("got %#v", res)
	}
}

func TestTerminalClient_NoLineItSendsIsOverTheLimit(t *testing.T) {
	f := newFake(t)
	if _, err := terminalFor(f.server()).Query(context.Background(), "SELECT "+strings.Repeat("x, ", 2000)+"y"); err != nil {
		t.Fatal(err)
	}
	for _, l := range f.lines {
		if len(l) > maxTerminalLine {
			t.Fatalf("sent a %d-character line", len(l))
		}
	}
}

func TestTerminalClient_ReusesOneSessionCookieAcrossQueries(t *testing.T) {
	// Each WebSocket without the session cookie takes a licence slot until the session times out; on
	// Community IRIS a dashboard ran out in minutes. One GET seeds the cookie, every connection reuses it.
	f := newFake(t)
	c := terminalFor(f.server())
	for i := 0; i < 3; i++ {
		if _, err := c.Query(context.Background(), "SELECT 1"); err != nil {
			t.Fatal(err)
		}
	}
	if f.gets != 1 {
		t.Fatalf("GET /api/atelier/ %d times, want once", f.gets)
	}
	for i, ck := range f.cookies {
		if !strings.Contains(ck, "CSPSESSIONID-SP-1-UP-api-atelier-=s1") {
			t.Fatalf("connection %d sent cookie %q", i, ck)
		}
	}
}

func TestTerminalClient_RefreshesTheSessionBeforeItTimesOut(t *testing.T) {
	f := newFake(t)
	c := terminalFor(f.server())
	now := time.Now()
	c.now = func() time.Time { return now }
	_, _ = c.Query(context.Background(), "SELECT 1")
	now = now.Add(sessionRefresh + time.Second)
	_, _ = c.Query(context.Background(), "SELECT 1")
	if f.gets != 2 {
		t.Fatalf("GET /api/atelier/ %d times, want 2", f.gets)
	}
}

func TestTerminalClient_RetriesOnceWhenTheTerminalHangsUpBeforeInit(t *testing.T) {
	f := newFake(t)
	f.closeFirst = 1
	if _, err := terminalFor(f.server()).Query(context.Background(), "SELECT 1"); err != nil {
		t.Fatal(err)
	}
	if f.gets != 2 || f.sessions != 2 {
		t.Fatalf("gets %d sessions %d, want a fresh session and one retry", f.gets, f.sessions)
	}
}

func TestTerminalClient_GivesUpWhenTheTerminalKeepsHangingUp(t *testing.T) {
	f := newFake(t)
	f.closeFirst = 5
	_, err := terminalFor(f.server()).Query(context.Background(), "SELECT 1")
	var unreach *UnreachableError
	if !errors.As(err, &unreach) {
		t.Fatalf("got %v", err)
	}
	if f.sessions != 2 {
		t.Fatalf("%d sessions, want 2", f.sessions)
	}
}

func TestTerminalClient_AWrongPasswordIsAnAuthError(t *testing.T) {
	f := newFake(t)
	_, err := terminalFor(f.server(), func(c *TerminalClientConfig) { c.Password = "nope" }).Query(context.Background(), "SELECT 1")
	var auth *AuthError
	if !errors.As(err, &auth) || auth.HTTPStatus != 401 {
		t.Fatalf("got %v", err)
	}
}

func TestTerminalClient_AnIRISWithoutTheTerminalSaysWhichVersionItNeeds(t *testing.T) {
	f := newFake(t)
	f.noTerminal = true
	_, err := terminalFor(f.server()).Query(context.Background(), "SELECT 1")
	var cfg *ConfigError
	if !errors.As(err, &cfg) || !strings.Contains(err.Error(), "2023.2") {
		t.Fatalf("got %v", err)
	}
}

func TestTerminalClient_AnUnknownNamespaceIsAConfigError(t *testing.T) {
	f := newFake(t)
	_, err := terminalFor(f.server(), func(c *TerminalClientConfig) { c.Namespace = "NOPE" }).Query(context.Background(), "SELECT 1")
	var cfg *ConfigError
	if !errors.As(err, &cfg) || !strings.Contains(err.Error(), "NOPE") {
		t.Fatalf("got %v", err)
	}
}

func TestTerminalClient_APrivilegeRefusalIsASQLError(t *testing.T) {
	f := newFake(t)
	f.answer = func(string) string {
		return "~IGD-ERR~" + b64("ERROR #5540: SQLCODE: -99 Message: User acme is not privileged for the operation") + "~IGD-END~"
	}
	_, err := terminalFor(f.server()).Query(context.Background(), "SELECT * FROM Globex_Events")
	var sqlErr *SQLError
	if !errors.As(err, &sqlErr) || sqlErr.Code != -99 || !strings.Contains(sqlErr.Message, "not privileged") {
		t.Fatalf("got %v", err)
	}
}

func TestTerminalClient_NoResultSaysWhatTheTerminalPrinted(t *testing.T) {
	f := newFake(t)
	f.answer = func(string) string { return "\x1b[31;1m<PROTECT>\x1b[0m" }
	_, err := terminalFor(f.server()).Query(context.Background(), "SELECT 1")
	if err == nil || !strings.Contains(err.Error(), "<PROTECT>") || strings.Contains(err.Error(), "\x1b") {
		t.Fatalf("got %v", err)
	}
}

func TestTerminalClient_CapsRowsAndBytes(t *testing.T) {
	f := newFake(t)
	f.answer = func(string) string { return rowsOutput(`[{"name":"v","type":5}]`, "[1]", "[2]", "[3]") }
	_, err := terminalFor(f.server(), func(c *TerminalClientConfig) { c.MaxRows = 2 }).Query(context.Background(), "SELECT 1")
	var tooMany *TooManyRowsError
	if !errors.As(err, &tooMany) {
		t.Fatalf("rows: got %v", err)
	}
	_, err = terminalFor(f.server(), func(c *TerminalClientConfig) { c.MaxResponseBytes = 50 }).Query(context.Background(), "SELECT 1")
	var tooLarge *TooLargeError
	if !errors.As(err, &tooLarge) {
		t.Fatalf("bytes: got %v", err)
	}
}

func TestTerminalClient_ATimeoutIsUnreachable(t *testing.T) {
	f := newFake(t)
	f.hang = true
	start := time.Now()
	_, err := terminalFor(f.server(), func(c *TerminalClientConfig) { c.Timeout = 300 * time.Millisecond }).Query(context.Background(), "SELECT 1")
	var unreach *UnreachableError
	if !errors.As(err, &unreach) {
		t.Fatalf("got %v", err)
	}
	if time.Since(start) > 3*time.Second {
		t.Fatalf("took %v", time.Since(start))
	}
}

func TestTerminalClient_IgnoresTheTimeoutOnTheHTTPClientItIsGiven(t *testing.T) {
	// http.Client.Timeout would cut the WebSocket off mid-query; the query's own timeout bounds it instead.
	f := newFake(t)
	srv := f.server()
	c := terminalFor(srv, func(c *TerminalClientConfig) { c.HTTPClient = &http.Client{Timeout: time.Nanosecond} })
	if _, err := c.Query(context.Background(), "SELECT 1"); err != nil {
		t.Fatal(err)
	}
}

func TestTerminalClient_PingRunsSelectOne(t *testing.T) {
	f := newFake(t)
	var got string
	f.answer = func(sql string) string { got = sql; return rowsOutput(`[{"name":"x","type":5}]`, "[1]") }
	if err := terminalFor(f.server()).Ping(context.Background()); err != nil {
		t.Fatal(err)
	}
	if got != "SELECT 1" {
		t.Fatalf("ping ran %q", got)
	}
}

type metricsOnly struct{ IRISClient }

func (metricsOnly) Metrics(context.Context) ([]MetricSample, error) {
	return []MetricSample{{Name: "iris_up", Value: 1}}, nil
}

func TestTerminalClient_MetricsGoThroughTheWebPortClient(t *testing.T) {
	f := newFake(t)
	srv := f.server()
	samples, err := terminalFor(srv, func(c *TerminalClientConfig) { c.Metrics = metricsOnly{} }).Metrics(context.Background())
	if err != nil || len(samples) != 1 {
		t.Fatalf("got %v, %v", samples, err)
	}
	_, err = terminalFor(srv).Metrics(context.Background())
	var cfg *ConfigError
	if !errors.As(err, &cfg) {
		t.Fatalf("no metrics client: got %v", err)
	}
}
