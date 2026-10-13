# Draft: go-irisnative fails on floats with dropped zero bytes

A draft issue (and patch) for <https://github.com/caretdev/go-irisnative>. Not filed.

## Title

`invalid compact float data length` for doubles such as 0, 2.0, 0.5 or an AVG that lands on a whole number

## Version

v0.3.0, against IRIS Community 2026.1 (container `iris-community:2026.1`).

## Reproduce

```go
db, _ := sql.Open("iris", "iris://_SYSTEM:SYS@localhost:1972/USER")
rows, _ := db.Query("SELECT CAST(2 AS DOUBLE) AS x")
for rows.Next() {}
fmt.Println(rows.Err()) // invalid compact float data length
```

`CAST(0 AS DOUBLE)`, `CAST(0.5 AS DOUBLE)`, `CAST(-2 AS DOUBLE)`, `CAST(123456789.125 AS DOUBLE)` and `AVG(x)` over
`1.5` and `2.5` fail the same way (the last two with `invalid IEEE double data length`). `CAST(2.5 AS DOUBLE)` and
`CAST(3 AS DOUBLE)` work. The error surfaces from `rows.Err()`, and the whole result is lost.

## Cause

IRIS drops the low-order zero bytes of a float in the list item. Logged data for the failing values:

| value         | item type | data bytes             |
| ------------- | --------- | ---------------------- |
| 0             | 8         | (empty)                |
| 2.0           | 8         | `40`                   |
| -2.0          | 8         | `c0`                   |
| 0.5           | 8         | `3f`                   |
| 123456789.125 | 9         | six of the eight bytes |

The bytes kept are the most significant ones, in little-endian order. `asFloat64` accepts only 2, 4 or 8 bytes for
type 8 and exactly 8 for type 9.

## Fix

Shift the kept bytes back into place: for type 8 with 1 to 4 bytes, treat them as a float32 (`bits << 8*(4-n)`); for
5 to 7 bytes, and for type 9 with fewer than 8, treat them as a float64 (`bits << 8*(8-n)`); empty means 0. The patch
is in `third_party/go-irisnative/src/list/listitem.go` of the Grafana plugin, with a test,
`TestCompactFloatWithDroppedZeroBytes`, that fails on v0.3.0. Checked against 31 doubles on a real IRIS.

## Also seen

- A DML statement (`INSERT`, `UPDATE`, `DELETE`) run with `QueryContext` returns no error, but `rows.Err()` then
  reports `SQLCODE -400 ... <UNDEFINED>Server+485^%SYS.DBSRV` because the driver tries to fetch from a statement with
  no result set. `ExecContext` is fine. Callers that cannot know the statement type should check
  `rows.ColumnTypes()` for zero columns.
- `SQLError.SQLCode` is the magnitude (30 for "table not found") where IRIS says SQLCODE -30.
