import React, { ChangeEvent } from 'react';

import { QueryEditorProps, SelectableValue } from '@grafana/data';
import { InlineField, RadioButtonGroup, Stack, TextArea } from '@grafana/ui';

import { DataSource } from '../datasource';
import { IRISDataSourceOptions, IRISQuery, IRISQueryType } from '../types';

type Props = QueryEditorProps<DataSource, IRISQuery, IRISDataSourceOptions>;

const QUERY_TYPE_OPTIONS: Array<SelectableValue<IRISQueryType>> = [
  { label: 'SQL', value: 'sql', description: 'Run a SQL statement against IRIS' },
  { label: 'SAM metrics', value: 'sam_metrics', description: "Scrape IRIS's built-in /api/monitor/metrics endpoint" },
];

export function QueryEditor({ query, onChange, onRunQuery }: Props) {
  const queryType = query.queryType ?? 'sql';

  const onQueryTypeChange = (value: IRISQueryType) => {
    onChange({ ...query, queryType: value });
    onRunQuery();
  };

  const onQueryTextChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    onChange({ ...query, queryText: event.target.value });
  };

  return (
    <Stack direction="column" gap={1}>
      <InlineField label="Query type" labelWidth={16}>
        <RadioButtonGroup options={QUERY_TYPE_OPTIONS} value={queryType} onChange={onQueryTypeChange} />
      </InlineField>
      {queryType === 'sql' && (
        <InlineField label="SQL" labelWidth={16} grow tooltip="Any SQL statement IRIS's SQL engine can run.">
          <TextArea
            id="query-editor-query-text"
            onChange={onQueryTextChange}
            onBlur={onRunQuery}
            value={query.queryText ?? ''}
            rows={4}
            placeholder="SELECT TOP 100 * FROM SQLUser.MyTable"
          />
        </InlineField>
      )}
    </Stack>
  );
}
