package client

import (
	"encoding/base64"
	"errors"
	"reflect"
	"strings"
	"testing"
)

func b64(s string) string { return base64.StdEncoding.EncodeToString([]byte(s)) }

// rebuild runs the chunk lines the way the terminal would, for the two locals they set.
func rebuild(t *testing.T, lines []string) (program, sql string) {
	t.Helper()
	vars := map[string]string{}
	for _, l := range lines {
		switch {
		case l == `Kill  Set tP="",tS=""`:
			vars = map[string]string{"tP": "", "tS": ""}
		case strings.HasPrefix(l, "Set "):
			name, rest, _ := strings.Cut(strings.TrimPrefix(l, "Set "), "=")
			chunk := strings.TrimSuffix(strings.TrimPrefix(rest, name+`_"`), `"`)
			vars[name] += chunk
		}
	}
	p, err := base64.StdEncoding.DecodeString(vars["tP"])
	if err != nil {
		t.Fatal(err)
	}
	s, err := base64.StdEncoding.DecodeString(vars["tS"])
	if err != nil {
		t.Fatal(err)
	}
	return string(p), string(s)
}

func TestTerminalLines_EveryLineFitsTheTerminalsInputLimit(t *testing.T) {
	// The terminal drops a line of 427 characters or more without a word; 425 was measured to run.
	sql := "SELECT " + strings.Repeat("a, ", 4000) + "b FROM t"
	for i, l := range terminalLines(sql) {
		if len(l) > maxTerminalLine {
			t.Fatalf("line %d is %d characters: %.80s", i, len(l), l)
		}
	}
	if maxTerminalLine > 400 {
		t.Fatalf("the limit %d leaves no margin under the measured 425", maxTerminalLine)
	}
}

func TestTerminalLines_CarryTheProgramAndTheSQLAsData(t *testing.T) {
	sql := `SELECT 'é€ "quoted" ~IGD-OK~' AS s FROM t WHERE x = 'it''s'`
	lines := terminalLines(sql)
	program, got := rebuild(t, lines)
	if got != sql {
		t.Fatalf("SQL round trip: %q", got)
	}
	if program != terminalProgram {
		t.Fatal("the program does not round-trip")
	}
	if last := lines[len(lines)-1]; last != `Xecute $ZCVT($SYSTEM.Encryption.Base64Decode(tP),"I","UTF8")` {
		t.Fatalf("last line runs something else: %s", last)
	}
	for _, l := range lines {
		if strings.Contains(l, "SELECT") || strings.Contains(l, "it''s") {
			t.Fatalf("the SQL reached a terminal line as text, not base64: %s", l)
		}
	}
}

func TestTerminalLines_StartFromCleanLocals(t *testing.T) {
	if first := terminalLines("SELECT 1")[0]; !strings.HasPrefix(first, "Kill  ") {
		t.Fatalf("first line should clear the locals: %s", first)
	}
}

func TestTerminalProgram_PreparesWithPrivilegeChecking(t *testing.T) {
	// The whole point of this transport: %Prepare's second argument turns SQL privilege checking on.
	if !strings.Contains(terminalProgram, `%Prepare($ZCVT($SYSTEM.Encryption.Base64Decode(tS),"I","UTF8"),1)`) {
		t.Fatal("the program does not prepare with checkPriv=1")
	}
}

func feedAll(p *terminalOutput, chunks ...string) error {
	for _, c := range chunks {
		if err := p.feed(c); err != nil {
			return err
		}
	}
	return nil
}

func TestTerminalOutput_ParsesColumnsAndTypedRows(t *testing.T) {
	cols := `[{"name":"tp","type":9},{"name":"n","type":14},{"name":"b","type":16},{"name":"s","type":10}]`
	stream := "~IGD-COLS~" + b64(cols) + "~IGD-END~" +
		"~IGD-ROW~" + b64(`["1154712879006846976",3.25,true,"x"]`) + "~IGD-END~" +
		"~IGD-ROW~" + b64(`[null,null,null,""]`) + "~IGD-END~" +
		"~IGD-OK~\r\n\x1b[31;1m<EDITED>\x1b[0m"
	// Split everywhere: frames arrive in arbitrary pieces.
	for size := 1; size <= len(stream); size += 7 {
		p := newTerminalOutput(0, 0)
		var chunks []string
		for i := 0; i < len(stream); i += size {
			chunks = append(chunks, stream[i:min(i+size, len(stream))])
		}
		if err := feedAll(p, chunks...); err != nil {
			t.Fatalf("size %d: %v", size, err)
		}
		if !p.done {
			t.Fatalf("size %d: not done", size)
		}
		res, err := p.result()
		if err != nil {
			t.Fatal(err)
		}
		want := &QueryResult{
			Columns: []Column{{Name: "tp"}, {Name: "n"}, {Name: "b"}, {Name: "s"}},
			Rows:    []Row{{"1154712879006846976", 3.25, true, "x"}, {nil, nil, nil, ""}},
		}
		if !reflect.DeepEqual(res, want) {
			t.Fatalf("size %d: got %#v", size, res)
		}
	}
}

func TestTerminalOutput_IgnoresWhatTheTerminalPrintsAroundTheMarkers(t *testing.T) {
	p := newTerminalOutput(0, 0)
	err := feedAll(p, "\r\n\x1b[31;1m<EDITED>\x1b[0m\r\n", "~IGD-COLS~"+b64(`[{"name":"v","type":5}]`)+"~IGD-END~",
		"junk~IG", "D-ROW~"+b64("[1]")[:3], b64("[1]")[3:]+"~IGD-END~", "~IGD-OK~")
	if err != nil {
		t.Fatal(err)
	}
	res, _ := p.result()
	if len(res.Rows) != 1 || res.Rows[0][0] != 1.0 {
		t.Fatalf("got %#v", res)
	}
}

func TestTerminalOutput_TakesBase64WrappedAcrossLines(t *testing.T) {
	enc := b64(`[{"name":"v","type":10}]`)
	p := newTerminalOutput(0, 0)
	if err := feedAll(p, "~IGD-COLS~"+enc[:8]+"\r\n"+enc[8:]+"~IGD-END~~IGD-OK~"); err != nil {
		t.Fatal(err)
	}
	if res, _ := p.result(); res.Columns[0].Name != "v" {
		t.Fatalf("got %#v", res)
	}
}

func TestTerminalOutput_AnErrorIsASQLErrorWithItsSQLCODE(t *testing.T) {
	p := newTerminalOutput(0, 0)
	msg := "ERROR #5540: SQLCODE: -99 Message: User acme is not privileged for the operation"
	if err := feedAll(p, "~IGD-ERR~"+b64(msg)+"~IGD-END~"); err != nil {
		t.Fatal(err)
	}
	if !p.done {
		t.Fatal("an error ends the result")
	}
	_, err := p.result()
	var sqlErr *SQLError
	if !errors.As(err, &sqlErr) || sqlErr.Code != -99 || sqlErr.Message != msg {
		t.Fatalf("got %#v", err)
	}
}

func TestTerminalOutput_AnEmptyErrorIsStillAnError(t *testing.T) {
	p := newTerminalOutput(0, 0)
	_ = p.feed("~IGD-ERR~~IGD-END~")
	if _, err := p.result(); err == nil {
		t.Fatal("want an error")
	}
}

func TestTerminalOutput_AnErrorWithoutASQLCODEKeepsItsText(t *testing.T) {
	p := newTerminalOutput(0, 0)
	_ = p.feed("~IGD-ERR~" + b64("<UNDEFINED>x+1^y") + "~IGD-END~")
	_, err := p.result()
	var sqlErr *SQLError
	if !errors.As(err, &sqlErr) || sqlErr.Code != 0 || sqlErr.Message != "<UNDEFINED>x+1^y" {
		t.Fatalf("got %#v", err)
	}
}

func TestTerminalOutput_ANonSelectHasNoColumnsAndNoRows(t *testing.T) {
	p := newTerminalOutput(0, 0)
	_ = p.feed("~IGD-COLS~" + b64("[]") + "~IGD-END~~IGD-OK~")
	res, err := p.result()
	if err != nil || len(res.Columns) != 0 || len(res.Rows) != 0 {
		t.Fatalf("got %#v, %v", res, err)
	}
}

func TestTerminalOutput_RefusesMoreRowsThanTheCap(t *testing.T) {
	p := newTerminalOutput(0, 2)
	row := "~IGD-ROW~" + b64("[1]") + "~IGD-END~"
	err := feedAll(p, "~IGD-COLS~"+b64(`[{"name":"v","type":5}]`)+"~IGD-END~", row, row, row)
	var tooMany *TooManyRowsError
	if !errors.As(err, &tooMany) || tooMany.Limit != 2 {
		t.Fatalf("got %v", err)
	}
}

func TestTerminalOutput_RefusesMoreBytesThanTheCap(t *testing.T) {
	p := newTerminalOutput(100, 0)
	err := feedAll(p, strings.Repeat("x", 60), strings.Repeat("x", 60))
	var tooLarge *TooLargeError
	if !errors.As(err, &tooLarge) || tooLarge.Limit != 100 {
		t.Fatalf("got %v", err)
	}
}

func TestTerminalOutput_BadBase64OrJSONIsAnError(t *testing.T) {
	for _, s := range []string{"~IGD-ROW~!!!~IGD-END~", "~IGD-COLS~" + b64("{nope") + "~IGD-END~"} {
		if err := newTerminalOutput(0, 0).feed(s); err == nil {
			t.Fatalf("%q: want an error", s)
		}
	}
}

func TestTerminalOutput_ARowBeforeItsColumnsIsAnError(t *testing.T) {
	if err := newTerminalOutput(0, 0).feed("~IGD-ROW~" + b64("[1]") + "~IGD-END~"); err == nil {
		t.Fatal("want an error")
	}
}

func TestTerminalOutput_NotDoneUntilOKOrERR(t *testing.T) {
	p := newTerminalOutput(0, 0)
	_ = p.feed("~IGD-COLS~" + b64("[]") + "~IGD-END~")
	if p.done {
		t.Fatal("done too early")
	}
	if _, err := p.result(); err == nil {
		t.Fatal("result before the end should be an error")
	}
}
