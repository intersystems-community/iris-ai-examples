package client

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"regexp"
	"strconv"
	"strings"
)

// What the terminal client types, and how it reads the answer back.
//
// The Atelier terminal runs each line it is sent as ObjectScript, as the connecting user. Two measured
// limits shape what is sent: a line of 427 characters or more is dropped without any output (425 runs), and
// a line that compiles a new cached query outside a Try block prints <EDITED>. So the program below goes over
// as base64 in short chunks into a local, the SQL the same way into another, and one last line Xecutes the
// program. The SQL is only ever data: it is decoded inside the program and handed to %Prepare, never typed.
//
// The program writes every value base64-encoded between markers, so nothing a column holds can look like a
// marker, and anything else the terminal prints (prompts, <EDITED>, colour codes) is ignored.

// maxTerminalLine is the longest line sent, well under the measured 425.
const maxTerminalLine = 400

// terminalChunk is the base64 carried per line; the "Set tP=tP_" around it keeps the line under the limit.
const terminalChunk = 300

// b64Out is the ObjectScript that writes x as UTF-8 base64 with no line breaks.
func b64Out(x string) string {
	return `$SYSTEM.Encryption.Base64Encode($ZCVT(` + x + `,"O","UTF8"),1)`
}

// terminalProgram prepares tS with privilege checking on (the 1), runs it, and writes the columns, each row
// typed the way the REST transport types it (numbers, booleans, strings, null), then ~IGD-OK~ or ~IGD-ERR~.
// Client types 3, 5, 14, 15, 18 and 21 are numeric and 16 is BIT; everything else, timestamps included,
// stays a string, as /api/atelier returns it. %GetData gives "" for NULL and $C(0) for an empty string.
var terminalProgram = strings.Join([]string{
	`Set tOK=0,tE=""`,
	`Try {`,
	`Set tSt=##class(%SQL.Statement).%New(),tSC=tSt.%Prepare($ZCVT($SYSTEM.Encryption.Base64Decode(tS),"I","UTF8"),1)`,
	`If $SYSTEM.Status.IsError(tSC) { Set tE=$SYSTEM.Status.GetErrorText(tSC) }`,
	`Else { Set tR=tSt.%Execute()`,
	`If tR.%SQLCODE<0 { Set tE="SQLCODE: "_tR.%SQLCODE_" Message: "_tR.%Message }`,
	`Else { Set tA=[],tC=0`,
	`If $IsObject(tSt.%Metadata) { Set tM=tSt.%Metadata.columns,tC=tM.Count() For i=1:1:tC {`,
	`Set tO=tM.GetAt(i),tT=tO.clientType,tY(i)=$S(",3,5,14,15,18,21,"[(","_tT_","):"number",tT=16:"boolean",1:"string")`,
	`Do tA.%Push({"name":(tO.colName),"type":(tT)}) } }`,
	`Write "~IGD-COLS~",` + b64Out("tA.%ToJSON()") + `,"~IGD-END~"`,
	`While tR.%Next(.tSC) { Set tW=[] For i=1:1:tC { Set tV=tR.%GetData(i)`,
	`If tV="" { Do tW.%Push("","null") } ElseIf tV=$C(0) { Do tW.%Push("") } Else { Do tW.%Push(tV,tY(i)) } }`,
	`Write "~IGD-ROW~",` + b64Out("tW.%ToJSON()") + `,"~IGD-END~" }`,
	`If $SYSTEM.Status.IsError(tSC) { Set tE=$SYSTEM.Status.GetErrorText(tSC) }`,
	`ElseIf tR.%SQLCODE<0 { Set tE="SQLCODE: "_tR.%SQLCODE_" Message: "_tR.%Message }`,
	`Else { Set tOK=1 } } }`,
	`} Catch tX { Set tE=tX.DisplayString() }`,
	`If tOK { Write "~IGD-OK~" } Else { Write "~IGD-ERR~",` + b64Out("tE") + `,"~IGD-END~" }`,
}, " ")

// terminalLines is every line typed for one query: clear the locals, fill tP and tS, Xecute tP.
func terminalLines(sql string) []string {
	lines := []string{`Kill  Set tP="",tS=""`}
	lines = append(lines, chunkInto("tP", base64.StdEncoding.EncodeToString([]byte(terminalProgram)))...)
	lines = append(lines, chunkInto("tS", base64.StdEncoding.EncodeToString([]byte(sql)))...)
	return append(lines, `Xecute $ZCVT($SYSTEM.Encryption.Base64Decode(tP),"I","UTF8")`)
}

// chunkInto appends base64 text to a local, terminalChunk characters per line.
func chunkInto(name, text string) []string {
	var lines []string
	for len(text) > 0 {
		n := min(terminalChunk, len(text))
		lines = append(lines, "Set "+name+"="+name+`_"`+text[:n]+`"`)
		text = text[n:]
	}
	return lines
}

const (
	markerPrefix = "~IGD-"
	markerEnd    = "~IGD-END~"
)

var sqlcodeRe = regexp.MustCompile(`SQLCODE: (-?\d+)`)

// terminalOutput reads the program's output as it arrives, in pieces of any size.
type terminalOutput struct {
	maxBytes, maxRows int
	seen              int
	buf               string
	cols              []Column
	colsSeen          bool
	rows              []Row
	failed            bool
	errText           string
	// done is set once ~IGD-OK~ or ~IGD-ERR~ has been read.
	done bool
	// stray keeps the start of whatever the terminal printed outside the markers, to explain a missing result.
	stray strings.Builder
}

// newTerminalOutput caps the bytes and rows read; zero means no cap.
func newTerminalOutput(maxBytes, maxRows int) *terminalOutput {
	return &terminalOutput{maxBytes: maxBytes, maxRows: maxRows}
}

// feed takes the next piece of terminal output.
func (p *terminalOutput) feed(text string) error {
	p.seen += len(text)
	if p.maxBytes > 0 && p.seen > p.maxBytes {
		return &TooLargeError{Limit: int64(p.maxBytes)}
	}
	p.buf += text
	for !p.done {
		i := strings.Index(p.buf, markerPrefix)
		if i < 0 {
			// Keep a tail that might be the start of a marker split across pieces.
			keep := max(0, len(p.buf)-len(markerPrefix)+1)
			p.noteStray(p.buf[:keep])
			p.buf = p.buf[keep:]
			return nil
		}
		p.noteStray(p.buf[:i])
		p.buf = p.buf[i:]
		tagEnd := strings.Index(p.buf[len(markerPrefix):], "~")
		if tagEnd < 0 {
			return nil
		}
		tag := p.buf[len(markerPrefix) : len(markerPrefix)+tagEnd]
		body := p.buf[len(markerPrefix)+tagEnd+1:]
		if tag == "OK" {
			p.done, p.buf = true, ""
			return nil
		}
		end := strings.Index(body, markerEnd)
		if end < 0 {
			return nil
		}
		p.buf = body[end+len(markerEnd):]
		if err := p.take(tag, body[:end]); err != nil {
			return err
		}
	}
	return nil
}

// take handles one complete marked payload.
func (p *terminalOutput) take(tag, payload string) error {
	raw, err := base64.StdEncoding.DecodeString(strings.Join(strings.Fields(payload), ""))
	if err != nil {
		return fmt.Errorf("iris: unreadable terminal output: %w", err)
	}
	switch tag {
	case "COLS":
		var cols []struct {
			Name string `json:"name"`
		}
		if err := json.Unmarshal(raw, &cols); err != nil {
			return fmt.Errorf("iris: unreadable column list: %w", err)
		}
		p.cols, p.colsSeen = make([]Column, len(cols)), true
		for i, c := range cols {
			p.cols[i] = Column{Name: c.Name}
		}
	case "ROW":
		if !p.colsSeen {
			return fmt.Errorf("iris: a row arrived before its columns")
		}
		if p.maxRows > 0 && len(p.rows) >= p.maxRows {
			return &TooManyRowsError{Limit: p.maxRows}
		}
		var row Row
		if err := json.Unmarshal(raw, &row); err != nil {
			return fmt.Errorf("iris: unreadable row: %w", err)
		}
		p.rows = append(p.rows, row)
	case "ERR":
		p.failed, p.errText, p.done = true, string(raw), true
	default:
		return fmt.Errorf("iris: unknown terminal marker %q", tag)
	}
	return nil
}

func (p *terminalOutput) noteStray(s string) {
	if room := 500 - p.stray.Len(); room > 0 {
		p.stray.WriteString(s[:min(room, len(s))])
	}
}

// strayText is what the terminal printed outside the markers, without colour codes.
func (p *terminalOutput) strayText() string {
	return strings.TrimSpace(ansiRe.ReplaceAllString(p.stray.String(), ""))
}

var ansiRe = regexp.MustCompile("\x1b\\[[0-9;]*[A-Za-z]")

// result is the query's outcome once done.
func (p *terminalOutput) result() (*QueryResult, error) {
	if !p.done {
		return nil, fmt.Errorf("iris: the terminal returned no result")
	}
	if p.failed {
		code := 0
		if m := sqlcodeRe.FindStringSubmatch(p.errText); m != nil {
			code, _ = strconv.Atoi(m[1])
		}
		return nil, &SQLError{Message: p.errText, Code: code}
	}
	return &QueryResult{Columns: p.cols, Rows: p.rows}, nil
}
