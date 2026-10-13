# InterSystems IRIS data source for Grafana

Query InterSystems IRIS with SQL, and chart IRIS's built-in system metrics, from Grafana dashboards, Explore and
alert rules.

- **SQL** with time-range macros, time bucketing, dashboard variables, a row limit, and a Table or Time series format.
- **Two ways to connect**: IRIS's REST API (web port) or its native SuperServer port.
- **System metrics** from IRIS's built-in `/api/monitor/metrics` endpoint (the same data System Alerting and
  Monitoring reads).
- **Alerting**: queries run on the Grafana server, so alert rules can use them.
- **Read-only by default**, because of how IRIS's REST API handles permissions (see Security).

## Requirements

- Grafana 11.1 or later. Tested on Grafana 11.1.0 and 13.2.3.
- InterSystems IRIS reachable on its web port (52773 by default, or your web gateway's port) for the **REST API**
  connection, whose `/api/atelier` endpoint is part of every IRIS instance, or on its SuperServer port (1972) for
  the **Native** connection.
- For REST, an IRIS account that holds the `%Development` resource, which the REST API requires, and can read the
  tables you query. For Native, an account with `SELECT` on the tables you query and nothing more.

## Security

Read this before you connect a production instance.

- **Queries are read-only by default.** Only `SELECT` (and `WITH ... SELECT`) statements run, and only one per
  query. Anything else is refused before it reaches IRIS. The "Allow data changes" setting lifts this; leave it off
  unless nobody else can use the data source.
- **Prefer the Native connection for a shared or production instance.** It runs every query under the account's SQL
  privileges: in testing, a `SELECT`-only account was refused `INSERT`, `DELETE` and a read of `%SYS.Task`
  (SQLCODE -99). Its limits: the driver has no TLS option, so the connection is not encrypted, and it is alpha
  software (see Good to know).
- **IRIS permissions do not limit what the REST API can do.** In testing, an account holding `SELECT` on a single
  table could still delete its rows, read other namespaces and read the class dictionary through `/api/atelier`.
  Treat any account you give Grafana as able to read everything on that IRIS instance, and treat anyone who can
  edit a panel as having that same reach. Use a dedicated IRIS instance or namespace for dashboards, and restrict
  network access to the Grafana server.
- **Use HTTPS** between Grafana and IRIS. Credentials are sent with every request.
- **The metrics endpoint needs no login on a default IRIS.** Restrict who can reach it.

## Configure

Add the data source under Connections, then fill in:

- **Connection**: **REST API** (default) or **Native**.
- **Host** and **Web port**: where IRIS's web server answers. With a Native connection also set **SuperServer
  port** (1972 by default); the web port is then optional and used only for SAM metrics.
- **Namespace**: the namespace queries run in. Defaults to `USER`.
- **Username** and **Password**: the password is stored encrypted by Grafana and is never sent back to the browser.
- **Use HTTPS** and **Skip TLS verify**: skip verification only for a self-signed lab instance.
- **Allow data changes**: off by default (see Security).
- **Timeout**: seconds to wait for IRIS. Defaults to 30.
- **Row limit**: most rows any query returns. Empty means no limit. A query can set its own, which wins.
- With a Native connection: **Max open connections** (10), **Max idle connections** (5) and **Connection lifetime**
  (1800 seconds) tune the connection pool.

Select **Save & test**. "IRIS connection OK" means the credentials work and the REST API answered.

## Query

Choose a query type:

- **SQL** runs a statement. Choose **Time series** to plot the result: the first timestamp column becomes the time
  axis and text columns split the result into one series each. Add `ORDER BY` the time column. Choose **Table**
  to see rows as returned.
- **SAM metrics** returns IRIS's current system metrics as a table.

```sql
SELECT tp, host, cpu
FROM Metrics
WHERE $__timeFilter(tp) AND host IN ($host)
ORDER BY tp
```

### Macros

| Macro                     | Expands to                                                    |
| ------------------------- | ------------------------------------------------------------- |
| `$__timeFilter(col)`      | `col >= <start> AND col <= <end>` for the range               |
| `$__timeFrom()`           | the start of the dashboard time range                         |
| `$__timeTo()`             | the end of the dashboard time range                           |
| `$__timeFrom(col)`        | `col >= <start>`                                              |
| `$__timeTo(col)`          | `col <= <end>`                                                |
| `$__timeGroup(col, step)` | `col` rounded down to a whole number of steps, for `GROUP BY` |

`step` is `30s`, `5m`, `2h` or `1d`, or `$__interval` to follow the panel's resolution. IRIS buckets to the second,
so a step under a second (`500ms`) rounds up to one second. For a graph of hourly averages:

```sql
SELECT $__timeGroup(tp, 1h) AS bucket, AVG(cpu) AS cpu
FROM Metrics
WHERE $__timeFilter(tp)
GROUP BY $__timeGroup(tp, 1h)
ORDER BY bucket
```

Times are written in UTC as `CAST('YYYY-MM-DD HH:MM:SS' AS TIMESTAMP)`, which compares correctly against both kinds
of timestamp column IRIS has. If your server stores local time, convert the column in the query.

### Variables

Dashboard variables work in SQL. A multi-value variable becomes a quoted list for `IN (...)`: `'a','b'`. A
single value is inserted as written, so write your own quotes (`name = '$name'`). Quotes inside a value are
doubled. Use `${name:raw}` to insert a value exactly as it is.

## Alerting

Alert rules can use this data source. Macros work in alerts; dashboard variables do not, which is a Grafana rule
for all data sources.

## Good to know

- **NULL arrives as an empty string or 0.** The REST API does not send real nulls, so a NULL cannot be told from an
  empty value.
- **One statement per query.** Over REST, results over 64 MiB are refused; over Native, results over 1,000,000 rows.
  Narrow the query with `TOP`, a `WHERE` clause or `$__timeFilter`. A row limit cuts the result after IRIS has
  sent it and says so on the panel; it does not make IRIS do less work.
- **The Native connection uses the community [`go-irisnative`](https://github.com/caretdev/go-irisnative) driver**,
  which is alpha. Version 0.3.0 failed any query that returned a double such as `0`, `2.0` or an `AVG` that lands on
  a whole number. This plugin carries a one-file fix under `third_party/go-irisnative` (see its `PATCHES.md`)
  until upstream releases one. Native results otherwise read the same as REST: numbers, UTC times, and real NULLs.
- **Timestamps** in tables created with SQL `CREATE TABLE ... TIMESTAMP` are decoded for you. Other timestamps are
  read as UTC.
- The REST API returns each column's stored value. If a column looks odd, `CAST(col AS VARCHAR)` shows its
  displayed form.

## Troubleshooting

- **HTTP 401 or "authentication failed"**: the username or password is wrong, or the account lacks the
  `%Development` resource.
- **"could not reach the server"**: check the host, the web port and whether the Grafana server can reach it.
- **`SQLCODE -30`, table not found**: tables belong to a schema, for example `SQLUser.MyTable`, and to the
  namespace you configured.
- **"this data source is read-only"**: the statement is not a `SELECT`. See Security.

## Links

- Source and issues: <https://github.com/intersystems-community/iris-ai-examples>
- InterSystems IRIS documentation: <https://docs.intersystems.com>
