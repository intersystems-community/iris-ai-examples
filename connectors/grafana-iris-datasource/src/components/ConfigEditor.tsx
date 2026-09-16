import React, { ChangeEvent } from 'react';

import { DataSourcePluginOptionsEditorProps } from '@grafana/data';
import { InlineField, Input, SecretInput, Switch } from '@grafana/ui';

import { IRISDataSourceOptions, IRISSecureJsonData } from '../types';

interface Props extends DataSourcePluginOptionsEditorProps<IRISDataSourceOptions, IRISSecureJsonData> {}

const LABEL_WIDTH = 16;
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

  const updateJsonData = <K extends keyof IRISDataSourceOptions>(key: K, value: IRISDataSourceOptions[K]) => {
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
        <Switch id="config-editor-usehttps" value={jsonData.useHTTPS ?? false} onChange={onUseHTTPSChange} />
      </InlineField>
      <InlineField
        label="Skip TLS verify"
        labelWidth={LABEL_WIDTH}
        tooltip="Only for self-signed lab/demo instances. Disables certificate verification."
      >
        <Switch id="config-editor-skiptlsverify" value={jsonData.skipTLSVerify ?? false} onChange={onSkipTLSVerifyChange} />
      </InlineField>
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
    </>
  );
}
