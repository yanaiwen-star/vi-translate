const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

function readJson(relativePath) {
  return JSON.parse(fs.readFileSync(path.resolve(__dirname, relativePath), 'utf8'));
}

test('pins first compile to stable non-audit settings', () => {
  const project = readJson('../project.config.json');
  const privateProject = readJson('../project.private.config.json');
  const appJson = readJson('../app.json');

  assert.equal(project.libVersion, '3.15.2');
  assert.equal(privateProject.libVersion, '3.15.2');
  assert.equal(project.setting.autoAudits, false);
  assert.equal(privateProject.setting.autoAudits, false);
  assert.equal(project.projectArchitecture, undefined);
  assert.equal(appJson.permission, undefined);
});

test('avoids the object spread that imports a missing Babel runtime helper', () => {
  const source = fs.readFileSync(
    path.resolve(__dirname, '../pages/index/index.js'),
    'utf8'
  );

  assert.doesNotMatch(source, /\{\s*\.\.\.turn\s*,\s*\.\.\.patch\s*\}/);
  assert.doesNotMatch(source, /\{\s*\.\.\.turns\[pendingIndex\]/);
  assert.match(source, /Object\.assign\(\{\}, turn, patch\)/);
  assert.match(
    source,
    /Object\.assign\(\{\}, turns\[pendingIndex\], \{ responseId: stableId \}\)/
  );
});
