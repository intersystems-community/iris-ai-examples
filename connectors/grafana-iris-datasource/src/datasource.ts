import { CoreApp, DataSourceInstanceSettings, ScopedVars } from '@grafana/data';
import { DataSourceWithBackend, getTemplateSrv } from '@grafana/runtime';

import { DEFAULT_QUERY, IRISDataSourceOptions, IRISQuery } from './types';

/**
 * Frontend half of the datasource. All the real work — running SQL,
 * scraping SAM metrics, building data frames — happens in the Go backend
 * (pkg/plugin); this class just shapes queries before they're sent over
 * and decides which ones are worth sending at all.
 */
export class DataSource extends DataSourceWithBackend<IRISQuery, IRISDataSourceOptions> {
  constructor(instanceSettings: DataSourceInstanceSettings<IRISDataSourceOptions>) {
    super(instanceSettings);
  }

  getDefaultQuery(_: CoreApp): Partial<IRISQuery> {
    return DEFAULT_QUERY;
  }

  applyTemplateVariables(query: IRISQuery, scopedVars: ScopedVars) {
    return {
      ...query,
      queryText: getTemplateSrv().replace(query.queryText ?? '', scopedVars),
    };
  }

  filterQuery(query: IRISQuery): boolean {
    // SAM metrics queries carry no SQL text and are always runnable once
    // added; SQL queries need actual text.
    if (query.queryType === 'sam_metrics') {
      return true;
    }
    return !!query.queryText;
  }
}
