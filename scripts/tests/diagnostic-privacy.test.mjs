import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const source=await fs.readFile('workspace_next/frontend/lib/diagnosticPrivacy.js','utf8');
const {redactDiagnostic}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const original={receipt:{key:{scope:'123456789012'},provenance:{model_sha256:'1'.repeat(64)},
  detail:'arn:aws:iam::123456789012:role/example',numeric:123456789012}};
const redacted=redactDiagnostic(original);
assert.equal(redacted.receipt.key.scope,'[provider account hidden]');
assert.equal(redacted.receipt.detail,'arn:aws:iam::[account ID hidden]:role/example');
assert.equal(redacted.receipt.numeric,'[account ID hidden]');
assert.equal(redacted.receipt.provenance.model_sha256,'1'.repeat(64));
assert.equal(original.receipt.key.scope,'123456789012');
console.log('Diagnostic privacy: provider identifiers masked; stored evidence and hashes preserved.');
