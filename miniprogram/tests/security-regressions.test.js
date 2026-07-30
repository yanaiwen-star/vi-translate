const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('websocket JWT is sent only in the config packet, never in the URL', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../utils/live.js'), 'utf8');
  assert.doesNotMatch(source, /\?token=/);
  assert.match(source, /type:\s*'config',[\s\S]*token:\s*this\.token/);
});

test('refresh cleanup returns the finally chain instead of ignoring it', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../utils/api.js'), 'utf8');
  assert.match(source, /_refreshing\s*=\s*refreshRequest\.finally/);
  assert.doesNotMatch(source, /_refreshing\.finally\(\(\)\s*=>/);
});

test('payment page cancels deferred work when hidden or unloaded', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/pay/pay.js'), 'utf8');
  assert.match(source, /onHide\(\)[\s\S]*this\.clearTimers\(\)/);
  assert.match(source, /onUnload\(\)[\s\S]*this\.clearTimers\(\)/);
  assert.doesNotMatch(source, /setTimeout\(tick,/);
});
