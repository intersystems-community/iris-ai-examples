# InterSystems IRIS data source for Grafana

Query InterSystems IRIS with SQL, and chart IRIS's built-in system metrics, from Grafana dashboards, Explore and
alert rules.

- **SQL** with time-range macros, time bucketing, dashboard variables, a row limit, and a Table or Time series format.
- **Three ways to connect**: IRIS's REST API (web port), its web terminal (the same port, with the account's SQL
  privileges enforced), or its native SuperServer port.
- **Multi-tenant dashboards** on one shared IRIS, with the web terminal connection and a Grafana org per Tenant.
- **System metrics** from IRIS's built-in `/api/monitor/metrics` endpoint (the same data System Alerting and
  Monitoring reads).
- **Alerting**: queries run on the Grafana server, so alert rules can use them.
- **Read-only by default**, because of how IRIS's REST API handles permissions (see Security).

## Requirements

- Grafana 11.1 or later. Tested on Grafana 11.1.0 and 13.2.3.
- InterSystems IRIS reachable on its web port (52773 by default, or your web gateway's port) for the **REST API**
  connection, whose `/api/atelier` endpoint is part of every IRIS instance, or on its SuperServer port (1972) for
  the **Native** connection. The **Web terminal** connection uses the web port too, and needs IRIS 2023.2 or later.
- For REST, an IRIS account that holds the `%Development` resource, which the REST API requires, and can read the
  tables you query. For the web terminal, the same `%Development` resource plus `SELECT` on exactly what the
  account may read. For Native, an account with `SELECT` on the tables you query and nothing more.

## Security

Read this before you connect a production instance.

- **Queries are read-only by default.** Only `SELECT` (and `WITH ... SELECT`) statements run, and only one per
  query. Anything else is refused before it reaches IRIS. The "Allow data changes" setting lifts this; leave it off
  unless nobody else can use the data source.
- **Prefer the Web terminal connection for a shared or production instance.** It runs every query under the
  account's SQL privileges: in testing, an account granted `SELECT` on one view read that view and was refused the
  base table, another Tenant's view and a `DELETE` on its own view (SQLCODE -99), while the same account over REST
  read all of them. It uses the web port, so HTTPS and your web gateway apply as they do for REST.
- **The Native connection also enforces SQL privileges**, but its driver has no TLS option, so the connection is not
  encrypted, and it is alpha software (see Good to know).
- **The account still holds `%Development`**, as `/api/atelier` requires on any connection, so whoever knows its
  password can run ObjectScript on that IRIS. Grafana keeps the password encrypted and never sends it to the browser.
  The web terminal connection types a fixed program and passes the panel's SQL to it as base64 data, so a panel's
  SQL can never run as ObjectScript.
- **IRIS permissions do not limit what the REST API can do.** In testing, an account holding `SELECT` on a single
  table could still delete its rows, read other namespaces and read the class dictionary through `/api/atelier`.
  Treat any account you give Grafana as able to read everything on that IRIS instance, and treat anyone who can
  edit a panel as having that same reach. Use a dedicated IRIS instance or namespace for dashboards, and restrict
  network access to the Grafana server.
- **Use HTTPS** between Grafana and IRIS. Credentials are sent with every request.
- **The metrics endpoint needs no login on a default IRIS.** Restrict who can reach it.

## Configure

Add the data source under Connections, then fill in:

- **Connection**: **REST API** (default), **Web terminal** or **Native**.
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

For a column that holds time as an integer count of milliseconds since 1970:

| Macro                            | Expands to                                                           |
| -------------------------------- | -------------------------------------------------------------------- |
| `$__unixEpochMsFilter(col)`      | `col >= <start ms> AND col <= <end ms>`                              |
| `$__unixEpochMsFrom()`           | the start of the range, in epoch ms                                  |
| `$__unixEpochMsTo()`             | the end of the range, in epoch ms                                    |
| `$__unixEpochMsGroup(col, step)` | `col` rounded down to a whole number of steps, in ms (exact to 1 ms) |

A numeric column named `time` or `timeEnd` is read as a Unix epoch, in seconds, milliseconds, microseconds or
nanoseconds by its size, the convention Grafana's own SQL data sources use. So an integer-ms column becomes the time
axis with an alias. `TIME` is a reserved word in IRIS SQL, so quote it:

```sql
SELECT $__unixEpochMsGroup(Ts, 5m) AS "time", COUNT(*) AS events
FROM IrisEvents.Events
WHERE $__unixEpochMsFilter(Ts)
GROUP BY $__unixEpochMsGroup(Ts, 5m)
ORDER BY "time"
```

### Annotations

Any SQL query can be a dashboard annotation source (Dashboard settings, Annotations, this data source). Return a
column named `time`, and optionally `timeEnd` for a band, `text`, and `tags` as a comma-separated string:

```sql
SELECT Ts AS "time", TsEnd AS timeEnd, msg AS text, tags
FROM Deploys
WHERE $__unixEpochMsFilter(Ts)
```

On Grafana 13, an annotation query that uses a **Custom** or **Constant** dashboard variable does not run at all,
with no error. A **Text box** variable works, and so does every variable type on Grafana 11.1. Measured on
13.2.3; it is Grafana's behaviour, not this data source's.

### Variables

Dashboard variables work in SQL. A multi-value variable becomes a quoted list for `IN (...)`: `'a','b'`. A
single value is inserted as written, so write your own quotes (`name = '$name'`). Quotes inside a value are
doubled. Use `${name:raw}` to insert a value exactly as it is.

## Alerting

Alert rules can use this data source. Macros work in alerts; dashboard variables do not, which is a Grafana rule
for all data sources.

## Multi-tenant dashboards

To give several Tenants dashboards over one shared IRIS, with no Tenant able to see another's rows:

1. In IRIS, give each Tenant a view over the shared tables (`... WHERE TenantID = 'acme'`) and an account granted
   `SELECT` on that view only, plus `%Development`.
2. In Grafana, make an organisation per Tenant, with one data source using the **Web terminal** connection and that
   Tenant's account. Grafana OSS has no per-data-source permissions, so the organisation is the boundary; Grafana
   Enterprise and Cloud can restrict a data source to a team instead.
3. Add the Tenant's people to their organisation only.

A viewer can send any SQL to their data source through Grafana's query API, not just the panels' SQL. That is
why the boundary is in IRIS: the view and the grant decide what the account reads. With the **REST API**
connection the same setup leaks, because `/api/atelier` does not check the grant. `e2e/tenant-isolation.sh` builds
this setup against a real IRIS and Grafana and checks both: it passes with the web terminal and fails with
`TENANT_TRANSPORT=rest`.

## Good to know

- **NULL arrives as an empty string or 0 over REST.** The REST API does not send real nulls, so a NULL cannot be told
  from an empty value. The web terminal and Native connections send real nulls.
- **The web terminal is slower than REST**: each query opens a terminal session and types about ten short lines,
  about 250 ms on a local container against tens of milliseconds for REST. Panels still run in parallel. Its other
  results read the same as REST, which the tests check value by value.
- **One statement per query.** Over REST, results over 64 MiB are refused; over Native, results over 1,000,000 rows;
  over the web terminal, either.
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
- **`SQLCODE -99`, "not privileged for the operation"** (web terminal or Native): IRIS refused the account. Grant it
  `SELECT` on the table or view, or query one it can read.
- **"this IRIS has no web terminal"**: the web terminal connection needs IRIS 2023.2 or later. Use REST or Native.

## Links

- Source and issues: <https://github.com/intersystems-community/iris-ai-examples>
- InterSystems IRIS documentation: <https://docs.intersystems.com>
