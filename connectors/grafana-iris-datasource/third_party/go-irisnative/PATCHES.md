# Local changes to go-irisnative

This is `github.com/caretdev/go-irisnative` v0.3.0, copied here and wired in with a `replace` directive in the
plugin's `go.mod`, under its original Apache-2.0 licence (see `LICENSE`). Apache-2.0 asks that changes be
stated; they are:

1. `src/list/listitem.go`: decode floats whose low-order zero bytes IRIS dropped.

   IRIS sends `2.0` as the single byte `0x40`, `0.5` as `0x3F`, `0` as nothing, and `123456789.125` as six of its
   eight bytes. v0.3.0 accepted only 2, 4 or 8 bytes for a compact float and exactly 8 for an IEEE double, so a
   query that returned any such value, for example `AVG()` over `1.5` and `2.5`, failed whole with
   `invalid compact float data length` or `invalid IEEE double data length`. The kept bytes are the most
   significant ones, in little-endian order; they are now shifted back into place.

   Checked against a real IRIS 2026.1 with 31 doubles (0, 2, -2, 0.5, 3.75, 1024, 0.1, 1/3, 123456789.125,
   1E300, 2.5E10, 1E15, pi, and others): all decode to the value IRIS returns over REST.

   Regression test: `TestCompactFloatWithDroppedZeroBytes` in `src/list/listitem_test.go`. It fails on v0.3.0.

Drop this directory and the `replace` line once upstream releases the fix.
