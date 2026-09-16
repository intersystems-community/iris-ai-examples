import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

import { ConfigEditor } from './ConfigEditor';
import { IRISDataSourceOptions, IRISSecureJsonData } from '../types';

function baseOptions(
  overrides: Partial<IRISDataSourceOptions> = {}
): Parameters<typeof ConfigEditor>[0]['options'] {
  return {
    id: 1,
    uid: 'iris-1',
    orgId: 1,
    name: 'IRIS',
    type: 'intersystems-iris-datasource',
    typeName: 'InterSystems IRIS',
    typeLogoUrl: '',
    access: 'proxy',
    url: '',
    user: '',
    basicAuthUser: '',
    database: '',
    basicAuth: false,
    isDefault: false,
    jsonData: { host: '', ...overrides } as IRISDataSourceOptions,
    secureJsonFields: {},
    secureJsonData: {} as IRISSecureJsonData,
    readOnly: false,
    withCredentials: false,
  };
}

describe('ConfigEditor', () => {
  it('writes host into jsonData, never into secureJsonData', () => {
    const onOptionsChange = jest.fn();
    render(<ConfigEditor onOptionsChange={onOptionsChange} options={baseOptions()} />);

    fireEvent.change(screen.getByPlaceholderText('iris.example.com'), {
      target: { value: 'iris.mydomain.com' },
    });

    expect(onOptionsChange).toHaveBeenCalledWith(
      expect.objectContaining({
        jsonData: expect.objectContaining({ host: 'iris.mydomain.com' }),
      })
    );
    const call = onOptionsChange.mock.calls[0][0];
    expect(call.secureJsonData?.password).toBeUndefined();
  });

  it('writes the password only into secureJsonData', () => {
    const onOptionsChange = jest.fn();
    render(<ConfigEditor onOptionsChange={onOptionsChange} options={baseOptions()} />);

    fireEvent.change(screen.getByPlaceholderText('Enter password'), {
      target: { value: 'topsecret' },
    });

    expect(onOptionsChange).toHaveBeenCalledWith(
      expect.objectContaining({
        secureJsonData: { password: 'topsecret' },
      })
    );
    const call = onOptionsChange.mock.calls[0][0];
    expect(call.jsonData.password).toBeUndefined();
  });

  it('defaults the port placeholder to 52773', () => {
    render(<ConfigEditor onOptionsChange={jest.fn()} options={baseOptions()} />);
    expect(screen.getByPlaceholderText('52773')).toBeInTheDocument();
  });
});
