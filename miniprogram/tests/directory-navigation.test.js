const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');

test('bottom navigation is the stable five-tab translator platform', () => {
  const app = JSON.parse(fs.readFileSync(path.join(root, 'app.json'), 'utf8'));
  const actual = app.tabBar.list.map((item) => [item.pagePath, item.text]);
  assert.deepEqual(actual, [
    ['pages/index/index', '同传'],
    ['pages/services/services', '找翻译'],
    ['pages/ask/ask', '找业务'],
    ['pages/messages/messages', '常用语'],
    ['pages/profile/profile', '我的']
  ]);
});

test('ask and messages tabs do not expose upload or free chat controls', () => {
  const ask = fs.readFileSync(path.join(root, 'pages/ask/ask.wxml'), 'utf8');
  const messages = fs.readFileSync(path.join(root, 'pages/messages/messages.wxml'), 'utf8');
  assert.doesNotMatch(ask, /chooseImage|chooseMessageFile|<textarea|type=["']file/);
  assert.doesNotMatch(messages, /textarea|chat-input|发送消息/);
});

test('phrasebook is categorized, bilingual, copyable and has matching audio controls', () => {
  const page = fs.readFileSync(path.join(root, 'pages/messages/messages.wxml'), 'utf8');
  const logic = fs.readFileSync(path.join(root, 'pages/messages/messages.js'), 'utf8');
  const phrases = fs.readFileSync(path.join(root, 'pages/messages/phrases.js'), 'utf8');
  assert.match(page, /中越常用语/);
  assert.match(page, /user-select="true"/);
  assert.match(page, /data-lang="zh"/);
  assert.match(page, /data-lang="vi"/);
  assert.match(page, /<picker/);
  assert.match(page, /bindchange="onSceneChange"/);
  assert.match(logic, /createInnerAudioContext/);
  assert.match(logic, /static\/phrases/);
  assert.match(logic, /lang === 'vi' \? 'wav' : 'mp3'/);
  assert.ok((phrases.match(/name:/g) || []).length >= 8);
  assert.ok((phrases.match(/^\s+\['/gm) || []).length >= 40);
  assert.ok(phrases.indexOf("id: 'shopping'") < phrases.indexOf("id: 'greetings'"));
});

test('translation results are selectable and the home page enables sharing', () => {
  const page = fs.readFileSync(path.join(root, 'pages/index/index.wxml'), 'utf8');
  const logic = fs.readFileSync(path.join(root, 'pages/index/index.js'), 'utf8');
  assert.ok((page.match(/user-select="true"/g) || []).length >= 8);
  assert.match(logic, /showShareMenu/);
  assert.match(logic, /shareTimeline/);
});

test('directory shows only translators and business tab shows only business information', () => {
  const services = fs.readFileSync(path.join(root, 'pages/services/services.wxml'), 'utf8');
  const ask = fs.readFileSync(path.join(root, 'pages/ask/ask.wxml'), 'utf8');
  assert.match(services, /profile-card/);
  assert.doesNotMatch(services, /业务信息|需求说明|热门翻译场景|怎么选择更合适/);
  assert.match(ask, /找业务/);
  assert.match(ask, /business-card/);
  assert.doesNotMatch(ask, /免费发布需求|<input|<picker/);
});

test('business directory has a free publish entry and dedicated form', () => {
  const app = JSON.parse(fs.readFileSync(path.join(root, 'app.json'), 'utf8'));
  const list = fs.readFileSync(path.join(root, 'pages/ask/ask.wxml'), 'utf8');
  const publish = fs.readFileSync(path.join(root, 'pages/business-publish/business-publish.wxml'), 'utf8');
  const logic = fs.readFileSync(path.join(root, 'pages/business-publish/business-publish.js'), 'utf8');
  assert.ok(app.pages.includes('pages/business-publish/business-publish'));
  assert.match(list, /免费发布/);
  assert.match(publish, /业务说明/);
  assert.match(logic, /createNeed/);
});

test('empty my-needs page opens the publish form directly', () => {
  const page = fs.readFileSync(path.join(root, 'pages/my-needs/my-needs.wxml'), 'utf8');
  const logic = fs.readFileSync(path.join(root, 'pages/my-needs/my-needs.js'), 'utf8');
  assert.match(page, /发布需求/);
  assert.doesNotMatch(page, /去问翻译/);
  assert.match(logic, /business-publish\/business-publish/);
});
