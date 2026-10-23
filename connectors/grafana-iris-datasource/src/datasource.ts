import { CoreApp, DataSourceInstanceSettings, ScopedVars } from '@grafana/data';
import { DataSourceWithBackend, getTemplateSrv } from '@grafana/runtime';

import { DEFAULT_QUERY, IrisDataSourceOptions, IrisQuery } from './types';

/** Anything that can be a dashboard variable's value; Grafana hands arrays to multi-value variables. */
type VariableValue = string | number | Array<string | number>;
type VariableInfo = { multi?: boolean; includeAll?: boolean };

const quote = (v: string | number) => `'${String(v).replace(/'/g, "''")}'`;

/**
 * How a dashboard variable is written into SQL. Follows Grafana's own SQL data sources:
 *  - a multi-value (or include-all) variable becomes a quoted, comma-separated list, for IN (...);
 *  - a single value is inserted as written, so the query supplies its own quotes ('$host') or none
 *    (n < $n); use ${var:raw} to skip even the escaping below.
 * A single quote inside any value is doubled, so a value cannot close the quote around it.
 */
export function interpolateSqlVariable(value: VariableValue, variable: VariableInfo): string {
  if (typeof value === 'number') {
    return String(value);
  }
  if (typeof value === 'string') {
    return variable?.multi || variable?.includeAll ? quote(value) : value.replace(/'/g, "''");
  }
  return value.map(quote).join(',');
}

/**
 * Frontend half of the datasource. All the real work — running SQL,
 * scraping SAM metrics, building data frames — happens in the Go backend
 * (pkg/plugin); this class just shapes queries before they're sent over
 * and decides which ones are worth sending at all.
 */
export class DataSource extends DataSourceWithBackend<IrisQuery, IrisDataSourceOptions> {
  constructor(instanceSettings: DataSourceInstanceSettings<IrisDataSourceOptions>) {
    super(instanceSettings);
    // Standard annotation support: an annotation query uses the same editor and backend as a panel query.
    // Return columns named time (and optionally timeEnd), text and tags (comma-separated).
    this.annotations = {};
  }

  getDefaultQuery(_: CoreApp): Partial<IrisQuery> {
    return DEFAULT_QUERY;
  }

  applyTemplateVariables(query: IrisQuery, scopedVars: ScopedVars) {
    return {
      ...query,
      queryText: getTemplateSrv().replace(query.queryText ?? '', scopedVars, interpolateSqlVariable),
    };
  }

  filterQuery(query: IrisQuery): boolean {
    // SAM metrics queries carry no SQL text and are always runnable once
    // added; SQL queries need actual text.
    if (query.queryType === 'sam_metrics') {
      return true;
    }
    return !!query.queryText;
  }
}
