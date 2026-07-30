const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

function loadPage() {
  const stubs = {
    '../utils/recorder.js': { RecorderManager: class {} },
    '../utils/live.js': { LiveTranslate: class {} },
    '../utils/api.js': { request: async () => ({}) },
    '../utils/session.js': { ensureSession() {} }
  };
  for (const [relative, exports] of Object.entries(stubs)) {
    const modulePath = path.resolve(__dirname, relative);
    require.cache[modulePath] = { exports };
  }
  global.getApp = () => ({ updateQuota() {}, globalData: {} });
  global.wx = { showToast() {}, vibrateShort() {} };
  let config;
  global.Page = (value) => { config = value; };
  const pagePath = path.resolve(__dirname, '../pages/index/index.js');
  delete require.cache[pagePath];
  require(pagePath);
  const page = { ...config, data: { ...config.data } };
  page.setData = (next) => Object.assign(page.data, next);
  page.queueFaceTurnAudio = () => {};
  return page;
}

test('live and face text normalize Vietnamese combining marks to NFC', () => {
  const page = loadPage();
  const decomposed = 'Vie\u0323\u0302t Nam';

  page.updateDraft('source', decomposed);
  page.handleFaceMessage({ type: 'model_event', source_final: decomposed });

  assert.equal(page.data.sourceDraft, 'Việt Nam');
  assert.equal(page.data.faceTurns[0].src, 'Việt Nam');
});

test('default live target is Vietnamese', () => {
  const page = loadPage();

  assert.equal(page.data.targetLangs[page.data.targetIndex].code, 'vi');
});

test('changing live target language clears text from the previous language', () => {
  const page = loadPage();
  page.data.targetIndex = 0;
  page.data.sourceLines = ['旧中文原文'];
  page.data.sourceDraft = '旧中文原文草稿';
  page.data.translationLines = ['旧中文译文'];
  page.data.translationDraft = '旧中文译文草稿';

  page.onTargetLang({ detail: { value: 1 } });

  assert.equal(page.data.targetLangs[page.data.targetIndex].code, 'vi');
  assert.deepEqual(page.data.sourceLines, []);
  assert.equal(page.data.sourceDraft, '');
  assert.deepEqual(page.data.translationLines, []);
  assert.equal(page.data.translationDraft, '');
});

test('face history is visible only for its recorded language pair', () => {
  const page = loadPage();
  page.faceApplyLangs('zh', 'vi');
  const turn = Object.assign(page.faceMakeTurn('resp-1'), {
    src: '你好',
    tgt: 'Xin chào'
  });
  page.setData({ faceTurns: [turn] });
  page.refreshFaceVisibleTurns();
  assert.equal(page.data.faceVisibleTurns.length, 1);

  page.faceApplyLangs('vi', 'zh');
  assert.equal(page.data.faceVisibleTurns.length, 0);

  page.faceApplyLangs('zh', 'vi');
  assert.equal(page.data.faceVisibleTurns.length, 1);
  assert.equal(page.data.faceVisibleTurns[0].tgt, 'Xin chào');
});

test('translation text uses a Vietnamese-capable system font fallback', () => {
  const wxss = fs.readFileSync(
    path.resolve(__dirname, '../pages/index/index.wxss'),
    'utf8'
  );

  assert.match(wxss, /"Segoe UI", Arial, "Noto Sans", "Helvetica Neue", "PingFang SC"/);
  assert.match(wxss, /\.live-text[\s\S]*font-family:\s*inherit/);
  assert.match(wxss, /\.face-bubble[\s\S]*font-family:\s*inherit/);
});

module.exports = { loadPage };
