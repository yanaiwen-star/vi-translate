const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');

test('need management pages are registered and contain no upload or chat controls', () => {
  const app = JSON.parse(fs.readFileSync(path.join(root, 'app.json'), 'utf8'));
  ['pages/my-needs/my-needs', 'pages/matched-needs/matched-needs', 'pages/report-profile/report-profile']
    .forEach((page) => assert.ok(app.pages.includes(page), page));
  const sources = ['pages/my-needs/my-needs.wxml', 'pages/matched-needs/matched-needs.wxml']
    .map((file) => fs.readFileSync(path.join(root, file), 'utf8')).join('\n');
  assert.doesNotMatch(sources, /chooseImage|chooseMessageFile|<textarea|chat-input/);
});

test('need and report API functions are available', () => {
  const api = require('../utils/directory-api.js');
  ['listMyNeeds', 'withdrawNeed', 'listMatchedNeeds', 'respondToNeed', 'reportProfile']
    .forEach((name) => assert.equal(typeof api[name], 'function', name));
});

test('report page uses fixed reasons and limited note input', () => {
  const source = fs.readFileSync(path.join(root, 'pages/report-profile/report-profile.js'), 'utf8');
  const template = fs.readFileSync(path.join(root, 'pages/report-profile/report-profile.wxml'), 'utf8');
  assert.match(source, /fake_identity/);
  assert.match(source, /illegal_content/);
  assert.match(template, /maxlength="120"/);
});
