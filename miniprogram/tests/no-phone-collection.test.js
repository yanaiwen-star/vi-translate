const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '..');

function read(relative) {
  return fs.readFileSync(path.join(root, relative), 'utf8');
}

test('mini program has no user phone-number collection entry', () => {
  const sources = [
    read('app.js'),
    read('pages/profile/profile.js'),
    read('pages/profile/profile.wxml')
  ].join('\n');
  assert.doesNotMatch(sources, /getPhoneNumber/);
  assert.doesNotMatch(sources, /\/api\/wx\/phone/);
  assert.doesNotMatch(sources, /onBindPhone/);
});

