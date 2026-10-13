package client

import (
	"context"
	"errors"
	"net"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/caretdev/go-irisnative/src/connection"
)

func TestNativeDSN_CarriesEverythingTheDriverNeeds(t *testing.T) {
	cfg := NativeClientConfig{Host: "iris.example.com", Port: 1972, Namespace: "DEMO", Username: "grafana", Password: "s3cret", Timeout: 45 * time.Second}

	u, err := url.Parse(nativeDSN(cfg))

	if err != nil {
		t.Fatal(err)
	}
	pw, _ := u.User.Password()
	if u.Scheme != "iris" || u.Host != "iris.example.com:1972" || u.Path != "/DEMO" || u.User.Username() != "grafana" || pw != "s3cret" {
		t.Fatalf("unexpected DSN %s", u)
	}
	if got := u.Query().Get("query_timeout"); got != "45" {
		t.Fatalf("query_timeout = %q, want 45", got)
	}
}

func TestNativeDSN_APasswordWithPunctuationSurvivesTheURL(t *testing.T) {
	cfg := NativeClientConfig{Host: "h", Port: 1972, Namespace: "USER", Username: "u@corp", Password: "p@ss:w/rd?#%"}

	u, err := url.Parse(nativeDSN(cfg))

	if err != nil {
		t.Fatal(err)
	}
	pw, _ := u.User.Password()
	if u.User.Username() != "u@corp" || pw != "p@ss:w/rd?#%" {
		t.Fatalf("credentials were mangled: %q / %q", u.User.Username(), pw)
	}
	if u.Host != "h:1972" {
		t.Fatalf("host = %q", u.Host)
	}
}

func TestNativeDSN_AnIPv6HostIsBracketed(t *testing.T) {
	u, err := url.Parse(nativeDSN(NativeClientConfig{Host: "::1", Port: 1972, Namespace: "USER", Username: "u"}))
	if err != nil || u.Host != "[::1]:1972" {
		t.Fatalf("host = %q (%v)", u.Host, err)
	}
}

func TestConvertNativeValue(t *testing.T) {
	est := time.FixedZone("EDT", -4*3600)
	cases := []struct {
		name string
		in   any
		want any
	}{
		{"nil stays nil", nil, nil},
		{"string", "x", "x"},
		{"bool", true, true},
		{"float", 2.5, 2.5},
		{"int becomes float", 7, float64(7)},
		{"int64 becomes float", int64(7), float64(7)},
		{"int32 becomes float", int32(7), float64(7)},
		{"bytes become a string", []byte("abc"), "abc"},
		// The driver hands a time in the machine's zone; the same instant must come out as UTC wall time,
		// the way the REST path reports it, so one query reads the same over either transport.
		{"time is UTC", time.Date(2026, 10, 7, 8, 0, 10, 0, est), "2026-10-07 12:00:10"},
		{"fractional seconds kept", time.Date(2026, 10, 7, 12, 0, 10, 250000000, time.UTC), "2026-10-07 12:00:10.25"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := convertNativeValue(c.in); got != c.want {
				t.Fatalf("got %#v (%T), want %#v (%T)", got, got, c.want, c.want)
			}
		})
	}
}

func TestMapNativeError(t *testing.T) {
	// The driver reports the magnitude, 30, where IRIS says SQLCODE -30.
	sqlErr := &connection.SQLError{SQLCode: 30, Message: "[SQLCODE: <-30>:<Table or view not found>]"}
	var gotSQL *SQLError
	if err := mapNativeError(sqlErr); !errors.As(err, &gotSQL) || gotSQL.Code != -30 || !strings.Contains(gotSQL.Message, "Table or view not found") {
		t.Fatalf("a SQL error must keep IRIS's code and message, got %#v", err)
	}

	var gotAuth *AuthError
	if err := mapNativeError(errors.New("Access Denied")); !errors.As(err, &gotAuth) || gotAuth.HTTPStatus != 0 {
		t.Fatalf("a refused login is an AuthError with no HTTP status, got %#v", err)
	}
	if gotAuth.Error() != "iris: authentication failed" {
		t.Fatalf("a native login failure must not mention HTTP, got %q", gotAuth.Error())
	}

	var gotUnreach *UnreachableError
	refused := &net.OpError{Op: "dial", Net: "tcp", Err: errors.New("connection refused")}
	if err := mapNativeError(refused); !errors.As(err, &gotUnreach) {
		t.Fatalf("a refused connection is Unreachable, got %#v", err)
	}
	if err := mapNativeError(context.DeadlineExceeded); !errors.As(err, &gotUnreach) {
		t.Fatalf("a timeout is Unreachable, got %#v", err)
	}

	other := errors.New("something unexpected")
	if got := mapNativeError(other); got != other {
		t.Fatalf("an unknown error passes through unchanged, got %#v", got)
	}
	if mapNativeError(nil) != nil {
		t.Fatal("nil in, nil out")
	}
}

func TestNativeClient_MetricsNeedTheWebPort(t *testing.T) {
	c := NewNativeClient(NativeClientConfig{Host: "h", Port: 1972, Namespace: "USER", Username: "u"})
	defer c.Close()

	_, err := c.Metrics(context.Background())

	var cfgErr *ConfigError
	if !errors.As(err, &cfgErr) || !strings.Contains(err.Error(), "web port") {
		t.Fatalf("want a ConfigError telling the user to set the web port, got %v", err)
	}
}

type stubMetrics struct{ called bool }

func (s *stubMetrics) Query(context.Context, string) (*QueryResult, error) { return nil, nil }
func (s *stubMetrics) Ping(context.Context) error                          { return nil }
func (s *stubMetrics) Metrics(context.Context) ([]MetricSample, error) {
	s.called = true
	return []MetricSample{{Name: "iris_up", Value: 1}}, nil
}

func TestNativeClient_MetricsGoThroughTheWebPortClientWhenThereIsOne(t *testing.T) {
	m := &stubMetrics{}
	c := NewNativeClient(NativeClientConfig{Host: "h", Port: 1972, Namespace: "USER", Username: "u", Metrics: m})
	defer c.Close()

	got, err := c.Metrics(context.Background())

	if err != nil || !m.called || len(got) != 1 || got[0].Name != "iris_up" {
		t.Fatalf("metrics should come from the web-port client: %v %v %+v", err, m.called, got)
	}
}
