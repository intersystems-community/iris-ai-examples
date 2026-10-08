import { interpolateSqlVariable, DataSource } from './datasource';

// getTemplateSrv().replace calls the formatter once per variable with the variable's raw value(s).
// This stand-in does the same, so the tests exercise our formatter and not Grafana's.
jest.mock('@grafana/runtime', () => {
  const actual = jest.requireActual('@grafana/runtime');
  return {
    ...actual,
    getTemplateSrv: () => ({
      replace: (text: string, _scoped: unknown, format: (v: unknown, variable: unknown) => string) =>
        text
          .replace('$host', format(['a', "b'c"], { multi: true }))
          .replace('$one', format("o'neil", { multi: false }))
          .replace('$n', format(10, { multi: false })),
    }),
  };
});

describe('interpolateSqlVariable', () => {
  it('quotes and escapes every value of a multi-value variable', () => {
    expect(interpolateSqlVariable(['a', "b'c"], { multi: true })).toBe("'a','b''c'");
  });

  it('quotes a single value for include-all too, so IN (...) always has a list', () => {
    expect(interpolateSqlVariable('a', { includeAll: true })).toBe("'a'");
  });

  it('leaves a single value unquoted (the query supplies its own quotes) but escapes a quote in it', () => {
    expect(interpolateSqlVariable("o'neil", { multi: false })).toBe("o''neil");
  });

  it('passes numbers through untouched', () => {
    expect(interpolateSqlVariable(10, { multi: false })).toBe('10');
  });

  it('cannot be broken out of by a value that closes the quote', () => {
    const hostile = "x' OR '1'='1";
    expect(interpolateSqlVariable(hostile, { multi: false })).toBe("x'' OR ''1''=''1");
    expect(interpolateSqlVariable([hostile], { multi: true })).toBe("'x'' OR ''1''=''1'");
  });
});

describe('DataSource.applyTemplateVariables', () => {
  const ds = new DataSource({ id: 1, uid: 'x', name: 'iris', type: 'intersystems-iris-datasource', jsonData: {} } as any);

  it('interpolates dashboard variables into the SQL text', () => {
    const out = ds.applyTemplateVariables(
      { refId: 'A', queryText: "SELECT * FROM T WHERE host IN ($host) AND name = '$one' AND n < $n" } as any,
      {}
    );
    expect(out.queryText).toBe("SELECT * FROM T WHERE host IN ('a','b''c') AND name = 'o''neil' AND n < 10");
  });

  it('keeps the other query fields, including the format', () => {
    const out = ds.applyTemplateVariables({ refId: 'A', queryText: 'SELECT 1', format: 'time_series' } as any, {});
    expect(out.format).toBe('time_series');
  });
});
