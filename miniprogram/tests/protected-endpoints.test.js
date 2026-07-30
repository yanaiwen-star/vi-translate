const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('photo and text translation use the authenticated API wrapper', () => {
  const source = fs.readFileSync(
    path.resolve(__dirname, '../pages/index/index.js'),
    'utf8'
  );
  assert.match(source, /request\(\s*'POST',\s*'\/photo-translate'/);
  assert.match(source, /request\(\s*'POST',\s*'\/text-translate'/);
  assert.doesNotMatch(source, /const PHOTO_TRANSLATE_URL/);
  assert.doesNotMatch(source, /const TEXT_TRANSLATE_URL/);
});
