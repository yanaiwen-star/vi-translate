const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '..');

function read(relative) {
  return fs.readFileSync(path.join(root, relative), 'utf8');
}

test('mini program does not persist translation sessions or expose history page', () => {
  const index = read('pages/index/index.js');
  const appConfig = JSON.parse(read('app.json'));
  assert.doesNotMatch(index, /utils\/session|sessionUtil|saveMessage|ensureSession/);
  assert.ok(!appConfig.pages.includes('pages/history/history'));
  const tabPages = (appConfig.tabBar && appConfig.tabBar.list || []).map((item) => item.pagePath);
  assert.ok(!tabPages.includes('pages/history/history'));
});

test('translation content is not written to local storage', () => {
  const index = read('pages/index/index.js');
  const contentKeys = /sourceText|targetText|sourceLines|translationLines|faceTurns|photoSource|photoTarget/;
  const storageCalls = index.split(/\r?\n/).filter((line) => /setStorage/.test(line));
  assert.ok(storageCalls.every((line) => !contentKeys.test(line)));
});

