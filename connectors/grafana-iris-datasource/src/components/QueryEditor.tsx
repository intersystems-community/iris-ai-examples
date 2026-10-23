import React, { ChangeEvent } from 'react';

import { QueryEditorProps, SelectableValue } from '@grafana/data';
import { InlineField, Input, RadioButtonGroup, Stack, Text, TextArea } from '@grafana/ui';

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

  const onRowLimitChange = (event: ChangeEvent<HTMLInputElement>) => {
    const raw = event.target.value;
    onChange({ ...query, rowLimit: raw === '' ? undefined : Number(raw) });
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
        <InlineField
          label="Row limit"
          labelWidth={16}
          tooltip="Most rows this query returns. Empty uses the data source's row limit."
        >
          <Input
            id="query-editor-row-limit"
            type="number"
            min={1}
            value={query.rowLimit ?? ''}
            onChange={onRowLimitChange}
            onBlur={onRunQuery}
            placeholder="Data source default"
            width={24}
          />
        </InlineField>
      )}
      {queryType === 'sql' && (
        <Text variant="bodySmall" color="secondary">
          Macros: <code>$__timeFilter(column)</code>, <code>$__timeFrom()</code>, <code>$__timeTo()</code> follow the
          dashboard time range; <code>$__timeFrom(column)</code> and <code>$__timeTo(column)</code> add the comparison.{' '}
          <code>$__timeGroup(column, interval)</code> buckets a time column (30s, 5m, 2h, 1d or $__interval) for GROUP
          BY. For epoch-millisecond columns use <code>$__unixEpochMsFilter(column)</code> and{' '}
          <code>$__unixEpochMsGroup(column, interval)</code>; a numeric column named <code>&quot;time&quot;</code> is
          read as an epoch. For a graph, choose Time series and ORDER BY the time column.
        </Text>
      )}
    </Stack>
  );
}
