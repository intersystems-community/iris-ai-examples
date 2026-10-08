import React, { ChangeEvent } from 'react';

import { QueryEditorProps, SelectableValue } from '@grafana/data';
import { InlineField, RadioButtonGroup, Stack, Text, TextArea } from '@grafana/ui';

import { DataSource } from '../datasource';
import { IrisDataSourceOptions, IrisFormat, IrisQuery, IrisQueryType } from '../types';

type Props = QueryEditorProps<DataSource, IrisQuery, IrisDataSourceOptions>;

const QUERY_TYPE_OPTIONS: Array<SelectableValue<IrisQueryType>> = [
  { label: 'SQL', value: 'sql', description: 'Run a SQL statement against IRIS' },
  { label: 'SAM metrics', value: 'sam_metrics', description: "Scrape IRIS's built-in /api/monitor/metrics endpoint" },
];

const FORMAT_OPTIONS: Array<SelectableValue<IrisFormat>> = [
  { label: 'Table', value: 'table', description: 'Rows as returned' },
  {
    label: 'Time series',
    value: 'time_series',
    description: 'First timestamp column is time; text columns split the series',
  },
];

export function QueryEditor({ query, onChange, onRunQuery }: Props) {
  const queryType = query.queryType ?? 'sql';

  const onQueryTypeChange = (value: IrisQueryType) => {
    onChange({ ...query, queryType: value });
    onRunQuery();
  };

  const onFormatChange = (value: IrisFormat) => {
    onChange({ ...query, format: value });
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
      {queryType === 'sql' && (
        <InlineField label="Format" labelWidth={16}>
          <RadioButtonGroup options={FORMAT_OPTIONS} value={query.format ?? 'table'} onChange={onFormatChange} />
        </InlineField>
      )}
      {queryType === 'sql' && (
        <Text variant="bodySmall" color="secondary">
          Macros: <code>$__timeFilter(column)</code>, <code>$__timeFrom()</code>, <code>$__timeTo()</code> follow the
          dashboard time range. For a graph, choose Time series and ORDER BY the time column.
        </Text>
      )}
    </Stack>
  );
}
