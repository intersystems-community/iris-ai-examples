import React, { ChangeEvent } from 'react';

import { DataSourcePluginOptionsEditorProps } from '@grafana/data';
import { config } from '@grafana/runtime';
import { Alert, InlineField, InlineSwitch, Input, SecretInput } from '@grafana/ui';

import { IrisDataSourceOptions, IrisSecureJsonData } from '../types';

interface Props extends DataSourcePluginOptionsEditorProps<IrisDataSourceOptions, IrisSecureJsonData> {}

const LABEL_WIDTH = 20;
const FIELD_WIDTH = 40;

/**
 * The password NEVER goes in jsonData. Grafana stores jsonData in plain
 * text (queryable, exportable, shown in the UI); secureJsonData is
 * encrypted at rest and only readable by this plugin's backend, and even
 * then only as an already-decrypted value handed to the Go process — the
 * frontend never sees it again once saved. See pkg/plugin/models.go for
 * the backend side of this contract.
 */
export function ConfigEditor(props: Props) {
  const { onOptionsChange, options } = props;
  const { jsonData, secureJsonFields, secureJsonData } = options;

  const updateJsonData = <K extends keyof IrisDataSourceOptions>(key: K, value: IrisDataSourceOptions[K]) => {
    onOptionsChange({
      ...options,
      jsonData: {
        ...jsonData,
        [key]: value,
      },
    });
  };

  const onHostChange = (e: ChangeEvent<HTMLInputElement>) => updateJsonData('host', e.target.value);
  const onWebPortChange = (e: ChangeEvent<HTMLInputElement>) =>
    updateJsonData('webPort', e.target.value === '' ? undefined : Number(e.target.value));
  const onNamespaceChange = (e: ChangeEvent<HTMLInputElement>) => updateJsonData('namespace', e.target.value);
  const onUsernameChange = (e: ChangeEvent<HTMLInputElement>) => updateJsonData('username', e.target.value);
  const onUseHTTPSChange = (e: ChangeEvent<HTMLInputElement>) => updateJsonData('useHTTPS', e.target.checked);
  const onSkipTLSVerifyChange = (e: ChangeEvent<HTMLInputElement>) => updateJsonData('skipTLSVerify', e.target.checked);
  const onSecureSocksProxyChange = (e: ChangeEvent<HTMLInputElement>) =>
    updateJsonData('enableSecureSocksProxy', e.target.checked);
  const onAllowWritesChange = (e: ChangeEvent<HTMLInputElement>) => updateJsonData('allowWrites', e.target.checked);
  const onRowLimitChange = (e: ChangeEvent<HTMLInputElement>) =>
    updateJsonData('rowLimit', e.target.value === '' ? undefined : Number(e.target.value));
  const onTimeoutChange = (e: ChangeEvent<HTMLInputElement>) =>
    updateJsonData('timeoutSeconds', e.target.value === '' ? undefined : Number(e.target.value));

  const onPasswordChange = (e: ChangeEvent<HTMLInputElement>) => {
    onOptionsChange({
      ...options,
      secureJsonData: {
        password: e.target.value,
      },
    });
  };

  const onResetPassword = () => {
    onOptionsChange({
      ...options,
      secureJsonFields: {
        ...options.secureJsonFields,
        password: false,
      },
      secureJsonData: {
        ...options.secureJsonData,
        password: '',
      },
    });
  };

  return (
    <>
      <InlineField label="Host" labelWidth={LABEL_WIDTH} required tooltip="IRIS host name or IP address">
        <Input
          id="config-editor-host"
          onChange={onHostChange}
          value={jsonData.host ?? ''}
          placeholder="iris.example.com"
          width={FIELD_WIDTH}
        />
      </InlineField>
      <InlineField
        label="Web port"
        labelWidth={LABEL_WIDTH}
        tooltip="IRIS web server port (the one that serves the Management Portal and REST APIs). Defaults to 52773."
      >
        <Input
          id="config-editor-webport"
          onChange={onWebPortChange}
          value={jsonData.webPort ?? ''}
          placeholder="52773"
          type="number"
          width={FIELD_WIDTH}
        />
      </InlineField>
      <InlineField label="Namespace" labelWidth={LABEL_WIDTH} tooltip="IRIS namespace to run queries against. Defaults to USER.">
        <Input
          id="config-editor-namespace"
          onChange={onNamespaceChange}
          value={jsonData.namespace ?? ''}
          placeholder="USER"
          width={FIELD_WIDTH}
        />
      </InlineField>
      <InlineField label="Username" labelWidth={LABEL_WIDTH}>
        <Input
          id="config-editor-username"
          onChange={onUsernameChange}
          value={jsonData.username ?? ''}
          placeholder="_SYSTEM"
          width={FIELD_WIDTH}
        />
      </InlineField>
      <InlineField label="Password" labelWidth={LABEL_WIDTH} tooltip="Stored encrypted; never sent back to the browser.">
        <SecretInput
          id="config-editor-password"
          isConfigured={Boolean(secureJsonFields?.password)}
          value={secureJsonData?.password}
          placeholder="Enter password"
          width={FIELD_WIDTH}
          onReset={onResetPassword}
          onChange={onPasswordChange}
        />
      </InlineField>
      <InlineField label="Use HTTPS" labelWidth={LABEL_WIDTH} tooltip="Connect to the web port over TLS.">
        <InlineSwitch id="config-editor-usehttps" value={jsonData.useHTTPS ?? false} onChange={onUseHTTPSChange} />
      </InlineField>
      <InlineField
        label="Skip TLS verify"
        labelWidth={LABEL_WIDTH}
        tooltip="Only for self-signed lab/demo instances. Disables certificate verification."
      >
        <InlineSwitch id="config-editor-skiptlsverify" value={jsonData.skipTLSVerify ?? false} onChange={onSkipTLSVerifyChange} />
      </InlineField>
      {config.secureSocksDSProxyEnabled && (
        <InlineField
          label="Secure SOCKS proxy"
          labelWidth={LABEL_WIDTH}
          tooltip="Reach IRIS through Grafana's Private Data Source Connect, for an IRIS that Grafana Cloud cannot reach directly."
        >
          <InlineSwitch
            id="config-editor-securesocksproxy"
            value={jsonData.enableSecureSocksProxy ?? false}
            onChange={onSecureSocksProxyChange}
          />
        </InlineField>
      )}
      <InlineField
        label="Allow data changes"
        labelWidth={LABEL_WIDTH}
        tooltip="Off: only SELECT queries run. On: any SQL statement runs, including INSERT, UPDATE, DELETE and DROP."
      >
        <InlineSwitch id="config-editor-allowwrites" value={jsonData.allowWrites ?? false} onChange={onAllowWritesChange} />
      </InlineField>
      {jsonData.allowWrites && (
        <Alert severity="warning" title="Data changes are allowed">
          Anyone who can edit a panel using this data source can change or delete data in IRIS. IRIS does not limit
          what its REST API can do to the table privileges of the account, so only switch this on for a data source
          that nobody else can use.
        </Alert>
      )}
      <InlineField label="Timeout (seconds)" labelWidth={LABEL_WIDTH} tooltip="HTTP request timeout. Defaults to 30.">
        <Input
          id="config-editor-timeout"
          onChange={onTimeoutChange}
          value={jsonData.timeoutSeconds ?? ''}
          placeholder="30"
          type="number"
          width={FIELD_WIDTH}
        />
      </InlineField>
      <InlineField
        label="Row limit"
        labelWidth={LABEL_WIDTH}
        tooltip="Most rows any query returns; a query's own row limit overrides this. Empty means no limit."
      >
        <Input
          id="config-editor-rowlimit"
          onChange={onRowLimitChange}
          value={jsonData.rowLimit ?? ''}
          placeholder="No limit"
          type="number"
          min={1}
          width={FIELD_WIDTH}
        />
      </InlineField>
    </>
  );
}
