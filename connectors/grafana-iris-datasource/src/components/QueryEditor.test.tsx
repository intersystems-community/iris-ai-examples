import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

import { QueryEditor } from './QueryEditor';
import { IrisQuery } from '../types';

// The datasource instance is never touched by QueryEditor itself, so an
// empty stand-in satisfies the prop type without needing a real
// DataSource (which would need a live backend to construct properly).
const fakeDatasource = {} as any;

function baseQuery(overrides: Partial<IrisQuery> = {}): IrisQuery {
  return { refId: 'A', queryType: 'sql', queryText: '', ...overrides };
}

describe('QueryEditor', () => {
  it('renders the SQL text area when queryType is sql', () => {
    render(
      <QueryEditor
        datasource={fakeDatasource}
        query={baseQuery()}
        onChange={jest.fn()}
        onRunQuery={jest.fn()}
      />
    );
    expect(screen.getByPlaceholderText(/SELECT TOP 100/)).toBeInTheDocument();
  });

  it('hides the SQL text area when queryType is sam_metrics', () => {
    render(
      <QueryEditor
        datasource={fakeDatasource}
        query={baseQuery({ queryType: 'sam_metrics' })}
        onChange={jest.fn()}
        onRunQuery={jest.fn()}
      />
    );
    expect(screen.queryByPlaceholderText(/SELECT TOP 100/)).not.toBeInTheDocument();
  });

  it('calls onChange with the new queryText when the SQL text area changes', () => {
    const onChange = jest.fn();
    render(
      <QueryEditor
        datasource={fakeDatasource}
        query={baseQuery()}
        onChange={onChange}
        onRunQuery={jest.fn()}
      />
    );
    fireEvent.change(screen.getByPlaceholderText(/SELECT TOP 100/), {
      target: { value: 'SELECT 1' },
    });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ queryText: 'SELECT 1' }));
  });

  it('switches queryType and re-runs the query when the toggle changes', () => {
    const onChange = jest.fn();
    const onRunQuery = jest.fn();
    render(
      <QueryEditor
        datasource={fakeDatasource}
        query={baseQuery()}
        onChange={onChange}
        onRunQuery={onRunQuery}
      />
    );
    fireEvent.click(screen.getByText('SAM metrics'));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ queryType: 'sam_metrics' }));
    expect(onRunQuery).toHaveBeenCalled();
  });
});

describe('QueryEditor format', () => {
  it('offers Table and Time series for SQL queries', () => {
    render(<QueryEditor datasource={fakeDatasource} query={baseQuery()} onChange={jest.fn()} onRunQuery={jest.fn()} />);
    expect(screen.getByLabelText('Table')).toBeInTheDocument();
    expect(screen.getByLabelText('Time series')).toBeInTheDocument();
  });

  it('defaults to Table and saves the choice, then re-runs', () => {
    const onChange = jest.fn();
    const onRunQuery = jest.fn();
    render(<QueryEditor datasource={fakeDatasource} query={baseQuery()} onChange={onChange} onRunQuery={onRunQuery} />);
    expect(screen.getByLabelText('Table')).toBeChecked();

    fireEvent.click(screen.getByLabelText('Time series'));

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ format: 'time_series' }));
    expect(onRunQuery).toHaveBeenCalled();
  });

  it('does not show the format for SAM metrics', () => {
    render(
      <QueryEditor
        datasource={fakeDatasource}
        query={baseQuery({ queryType: 'sam_metrics' })}
        onChange={jest.fn()}
        onRunQuery={jest.fn()}
      />
    );
    expect(screen.queryByLabelText('Time series')).not.toBeInTheDocument();
  });

  it('documents the macros next to the SQL box', () => {
    render(<QueryEditor datasource={fakeDatasource} query={baseQuery()} onChange={jest.fn()} onRunQuery={jest.fn()} />);
    expect(screen.getByText(/\$__timeFilter\(column\)/)).toBeInTheDocument();
  });
});
