import { DataSourceJsonData } from '@grafana/data';
import { DataQuery } from '@grafana/schema';

/** The two kinds of query this datasource's backend understands. Keep in
 * sync with pkg/plugin/datasource.go's QueryTypeSQL / QueryTypeSAMMetrics
 * constants. */
export type IrisQueryType = 'sql' | 'sam_metrics';

/** Keep in sync with pkg/plugin/models.go's TransportREST / TransportTerminal / TransportNative. */
export type IrisTransport = 'rest' | 'terminal' | 'native';

export interface IrisQuery extends DataQuery {
  queryType?: IrisQueryType;
  /** The SQL statement to run. Ignored when queryType is 'sam_metrics'. */
  queryText?: string;
  /** 'table' (default) returns rows as they are; 'time_series' makes the result plottable. */
  format?: IrisFormat;
  /** Caps the rows this query returns; overrides the data source's row limit. Unset or 0: use the data source's. */
  rowLimit?: number;
}

/** Keep in sync with pkg/plugin/timeseries.go's FormatTable / FormatTimeSeries. */
export type IrisFormat = 'table' | 'time_series';

export const DEFAULT_QUERY: Partial<IrisQuery> = {
  queryType: 'sql',
  queryText: '',
  format: 'table',
};

/**
 * Non-secret configuration for one IRIS datasource instance. This is
 * stored as plain JSON by Grafana (jsonData) and is visible to anyone who
 * can view the datasource's settings — the password is deliberately not
 * here, see IrisSecureJsonData.
 */
export interface IrisDataSourceOptions extends DataSourceJsonData {
  /** IRIS host name or IP address. */
  host?: string;
  /** IRIS web server port. Defaults to 52773. */
  webPort?: number;
  /** IRIS namespace to run queries against. Defaults to USER. */
  namespace?: string;
  username?: string;
  useHTTPS?: boolean;
  skipTLSVerify?: boolean;
  timeoutSeconds?: number;
  /** Lifts the backend's read-only guard (pkg/plugin/readonly.go). Off unless set. */
  allowWrites?: boolean;
  /** How the backend reaches IRIS: 'rest' (default, the web port), 'terminal' (the web port's terminal
   * WebSocket, under the account's SQL privileges) or 'native' (the SuperServer). */
  transport?: IrisTransport;
  /** IRIS SuperServer port for the native transport. Defaults to 1972. */
  superserverPort?: number;
  /** Connection pool for the native transport. */
  maxOpenConns?: number;
  maxIdleConns?: number;
  connMaxLifetimeSeconds?: number;
  /** Caps the rows any query returns (a query's own rowLimit overrides it). Unset: no cap. */
  rowLimit?: number;
  /** Route requests through Grafana's secure SOCKS proxy (Private Data Source Connect). */
  enableSecureSocksProxy?: boolean;
}

/**
 * Secret configuration for one IRIS datasource instance. Grafana encrypts
 * this at rest and never sends it back to the frontend after it has been
 * saved once — only isConfigured flags come back, in secureJsonFields.
 */
export interface IrisSecureJsonData {
  password?: string;
}
