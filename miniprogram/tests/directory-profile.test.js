const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');

test('profile detail blocks contact requests for examples', () => {
  const source = fs.readFileSync(path.join(root, 'pages/translator-detail/translator-detail.js'), 'utf8');
  const template = fs.readFileSync(path.join(root, 'pages/translator-detail/translator-detail.wxml'), 'utf8');
  assert.match(source, /is_example|contact_request_allowed/);
  assert.match(template, /示例资料不能申请联系方式/);
  assert.match(template, /未认证，请自行核实/);
});

test('free onboarding keeps verification optional and contacts voluntary', () => {
  const source = fs.readFileSync(path.join(root, 'pages/translator-edit/translator-edit.js'), 'utf8');
  const template = fs.readFileSync(path.join(root, 'pages/translator-edit/translator-edit.wxml'), 'utf8');
  assert.match(template, /实名认证（自愿）/);
  assert.match(template, /联系方式默认隐藏/);
  assert.doesNotMatch(source + template, /getPhoneNumber/);
  assert.match(source, /saveError/);
});

test('My page exposes self-service management without removing existing quota', () => {
  const template = fs.readFileSync(path.join(root, 'pages/profile/profile.wxml'), 'utf8');
  assert.match(template, /免费入驻|我的译员名片/);
  assert.match(template, /联系申请/);
  assert.match(template, /我的翻译需求/);
  assert.match(template, /剩余同传时长/);
});

test('directory API exposes profile and authorization methods', () => {
  const api = require('../utils/directory-api.js');
  [
    'getProfile', 'getMyProfile', 'createProfile', 'updateProfile',
    'requestContact', 'listContactRequests', 'approveContact',
    'rejectContact', 'revokeContact', 'getGrantedContact'
  ].forEach((name) => assert.equal(typeof api[name], 'function', name));
});

test('missing translator profile is handled as a normal empty state', () => {
  const myPage = fs.readFileSync(path.join(root, 'pages/profile/profile.js'), 'utf8');
  const editPage = fs.readFileSync(path.join(root, 'pages/translator-edit/translator-edit.js'), 'utf8');
  assert.match(myPage, /profile\.exists !== false/);
  assert.match(editPage, /item\.exists === false/);
});
