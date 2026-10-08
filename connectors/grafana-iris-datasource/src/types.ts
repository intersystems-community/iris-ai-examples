import { DataSourceJsonData } from '@grafana/data';
import { DataQuery } from '@grafana/schema';

/** The two kinds of query this datasource's backend understands. Keep in
 * sync with pkg/plugin/datasource.go's QueryTypeSQL / QueryTypeSAMMetrics
 * constants. */
export type IrisQueryType = 'sql' | 'sam_metrics';

export interface IrisQuery extends DataQuery {
  queryType?: IrisQueryType;
  /** The SQL statement to run. Ignored when queryType is 'sam_metrics'. */
  queryText?: string;
  /** 'table' (default) returns rows as they are; 'time_series' makes the result plottable. */
  format?: IrisFormat;
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
}

/**
 * Secret configuration for one IRIS datasource instance. Grafana encrypts
 * this at rest and never sends it back to the frontend after it has been
 * saved once — only isConfigured flags come back, in secureJsonFields.
 */
export interface IrisSecureJsonData {
  password?: string;
}
