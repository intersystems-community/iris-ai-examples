import { DataSourceJsonData } from '@grafana/data';
import { DataQuery } from '@grafana/schema';

/** The two kinds of query this datasource's backend understands. Keep in
 * sync with pkg/plugin/datasource.go's QueryTypeSQL / QueryTypeSAMMetrics
 * constants. */
export type IRISQueryType = 'sql' | 'sam_metrics';

export interface IRISQuery extends DataQuery {
  queryType?: IRISQueryType;
  /** The SQL statement to run. Ignored when queryType is 'sam_metrics'. */
  queryText?: string;
}

export const DEFAULT_QUERY: Partial<IRISQuery> = {
  queryType: 'sql',
  queryText: '',
};

/**
 * Non-secret configuration for one IRIS datasource instance. This is
 * stored as plain JSON by Grafana (jsonData) and is visible to anyone who
 * can view the datasource's settings — the password is deliberately not
 * here, see IRISSecureJsonData.
 */
export interface IRISDataSourceOptions extends DataSourceJsonData {
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
}

/**
 * Secret configuration for one IRIS datasource instance. Grafana encrypts
 * this at rest and never sends it back to the frontend after it has been
 * saved once — only isConfigured flags come back, in secureJsonFields.
 */
export interface IRISSecureJsonData {
  password?: string;
}
