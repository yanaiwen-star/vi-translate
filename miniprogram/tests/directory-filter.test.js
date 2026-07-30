const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const directory = require('../utils/directory.js');

test('directory query omits empty values and keeps combined filters', () => {
  assert.deepEqual(directory.buildDirectoryQuery({
    language: 'vi', country: 'VN', city: '', service: 'business', page: 1
  }), { language: 'vi', country: 'VN', service: 'business', page: 1 });
});

test('Vietnamese profiles sort before other languages with stable ids', () => {
  const result = directory.mergeAndSortProfiles([
    { id: 'z', language_codes: ['en'], completeness_score: 100 },
    { id: 'b', language_codes: ['vi'], completeness_score: 60 },
    { id: 'a', language_codes: ['vi'], completeness_score: 60 }
  ]);
  assert.deepEqual(result.map((item) => item.id), ['a', 'b', 'z']);
});

test('directory UI keeps example disclosure and avoids object spread helpers', () => {
  const services = fs.readFileSync(path.join(__dirname, '../pages/services/services.js'), 'utf8');
  assert.match(services, /示例资料·招募中/);
  assert.doesNotMatch(services, /\.\.\.[A-Za-z_$][\w$]*\s*[,}]/);
});
