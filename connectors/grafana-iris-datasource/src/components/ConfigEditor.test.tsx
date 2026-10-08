import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { config } from '@grafana/runtime';

import { ConfigEditor } from './ConfigEditor';
import { IrisDataSourceOptions, IrisSecureJsonData } from '../types';

function baseOptions(
  overrides: Partial<IrisDataSourceOptions> = {}
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
    jsonData: { host: '', ...overrides } as IrisDataSourceOptions,
    secureJsonFields: {},
    secureJsonData: {} as IrisSecureJsonData,
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

describe('ConfigEditor read-only guard', () => {
  it('shows "Allow data changes" switched off by default', () => {
    render(<ConfigEditor onOptionsChange={jest.fn()} options={baseOptions()} />);
    expect(screen.getByLabelText(/Allow data changes/i)).not.toBeChecked();
  });

  it('writes allowWrites into jsonData when switched on', () => {
    const onOptionsChange = jest.fn();
    render(<ConfigEditor onOptionsChange={onOptionsChange} options={baseOptions()} />);

    fireEvent.click(screen.getByLabelText(/Allow data changes/i));

    expect(onOptionsChange).toHaveBeenCalledWith(
      expect.objectContaining({ jsonData: expect.objectContaining({ allowWrites: true }) })
    );
  });

  it('says what the switch costs', () => {
    render(<ConfigEditor onOptionsChange={jest.fn()} options={baseOptions({ allowWrites: true })} />);
    expect(screen.getByText(/anyone who can edit a panel/i)).toBeInTheDocument();
  });
});

describe('ConfigEditor secure proxy', () => {
  afterEach(() => {
    config.secureSocksDSProxyEnabled = false;
  });

  it('offers the secure SOCKS proxy only when this Grafana has it enabled', () => {
    config.secureSocksDSProxyEnabled = false;
    const { unmount } = render(<ConfigEditor onOptionsChange={jest.fn()} options={baseOptions()} />);
    expect(screen.queryByLabelText(/Secure SOCKS proxy/i)).not.toBeInTheDocument();
    unmount();

    config.secureSocksDSProxyEnabled = true;
    render(<ConfigEditor onOptionsChange={jest.fn()} options={baseOptions()} />);
    expect(screen.getByLabelText(/Secure SOCKS proxy/i)).toBeInTheDocument();
  });

  it('writes enableSecureSocksProxy into jsonData', () => {
    config.secureSocksDSProxyEnabled = true;
    const onOptionsChange = jest.fn();
    render(<ConfigEditor onOptionsChange={onOptionsChange} options={baseOptions()} />);

    fireEvent.click(screen.getByLabelText(/Secure SOCKS proxy/i));

    expect(onOptionsChange).toHaveBeenCalledWith(
      expect.objectContaining({ jsonData: expect.objectContaining({ enableSecureSocksProxy: true }) })
    );
  });
});

