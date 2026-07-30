const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '..');

test('BYOK settings page is registered and live config sends only provider mode', () => {
  const appJson = JSON.parse(fs.readFileSync(path.join(root, 'app.json'), 'utf8'));
  assert.ok(appJson.pages.includes('pages/qwen-settings/qwen-settings'));
  const live = fs.readFileSync(path.join(root, 'utils/live.js'), 'utf8');
  assert.match(live, /provider_mode:\s*this\.providerMode/);
  assert.doesNotMatch(live, /api_key\s*:/);
});

test('realtime camera is disabled while explicit photo translation remains', () => {
  const live = fs.readFileSync(path.join(root, 'utils/live.js'), 'utf8');
  const index = fs.readFileSync(path.join(root, 'pages/index/index.js'), 'utf8');
  assert.doesNotMatch(live, /image_frame/);
  assert.match(live, /input_mode:\s*'mic'/);
  assert.match(index, /sourceType:\s*\['album',\s*'camera'\]/);
  assert.match(index, /'\/photo-translate'/);
});
