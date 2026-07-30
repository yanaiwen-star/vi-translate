const test = require('node:test');
const assert = require('node:assert/strict');
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
  page.handleCompleteAudio = () => {};
  page.queueFaceTurnAudio = () => {};
  return page;
}

function completeTextResponse(page, responseId, source, translation) {
  page.handleFaceMessage({ type: 'model_event', source_final: source });
  page.handleFaceMessage({
    type: 'model_event',
    response_started: true,
    response_id: responseId
  });
  page.handleFaceMessage({
    type: 'model_event',
    translation_final: translation,
    response_id: responseId
  });
  page.handleFaceMessage({
    type: 'model_event',
    response_done: true,
    response_id: responseId
  });
}

test('source, translation and audio with one response id share one turn', () => {
  const page = loadPage();
  page.data.faceSide = 'mine';

  page.handleFaceMessage({ type: 'model_event', source_final: '你好' });
  page.handleFaceMessage({
    type: 'model_event',
    response_started: true,
    response_id: 'r1'
  });
  page.handleFaceMessage({
    type: 'model_event',
    translation_final: 'Xin chào',
    response_id: 'r1'
  });
  page.handleFaceMessage({
    type: 'model_audio_wav',
    audio: 'wav1',
    response_id: 'r1'
  });
  page.handleFaceMessage({
    type: 'model_event',
    response_done: true,
    response_id: 'r1'
  });

  assert.equal(page.data.faceTurns.length, 1);
  assert.deepEqual(
    {
      responseId: page.data.faceTurns[0].responseId,
      side: page.data.faceTurns[0].side,
      src: page.data.faceTurns[0].src,
      tgt: page.data.faceTurns[0].tgt,
      audioB64: page.data.faceTurns[0].audioB64,
      responseDone: page.data.faceTurns[0].responseDone
    },
    {
      responseId: 'r1',
      side: 'mine',
      src: '你好',
      tgt: 'Xin chào',
      audioB64: 'wav1',
      responseDone: true
    }
  );
});

test('late audio stays with its own response instead of the latest turn', () => {
  const page = loadPage();
  completeTextResponse(page, 'r1', '第一句', 'Câu một');
  completeTextResponse(page, 'r2', '第二句', 'Câu hai');

  page.handleFaceMessage({
    type: 'model_audio_wav',
    audio: 'wav1',
    response_id: 'r1'
  });

  assert.equal(page.data.faceTurns[0].audioB64, 'wav1');
  assert.equal(page.data.faceTurns[1].audioB64, '');
});

test('turn keeps the speaker side captured when the response starts', () => {
  const page = loadPage();
  page.data.faceSide = 'peer';
  page.handleFaceMessage({ type: 'model_event', source_final: 'Hello' });
  page.handleFaceMessage({
    type: 'model_event',
    response_started: true,
    response_id: 'r-side'
  });

  page.data.faceSide = 'mine';
  page.handleFaceMessage({
    type: 'model_event',
    translation_final: '你好',
    response_id: 'r-side'
  });

  assert.equal(page.data.faceTurns[0].side, 'peer');
});

test('a new source after response_done waits for the next response turn', () => {
  const page = loadPage();
  completeTextResponse(page, 'r1', '第一句', 'Câu một');

  page.handleFaceMessage({ type: 'model_event', source_final: '第二句' });
  page.handleFaceMessage({
    type: 'model_event',
    response_started: true,
    response_id: 'r2'
  });
  page.handleFaceMessage({
    type: 'model_event',
    translation_final: 'Câu hai',
    response_id: 'r2'
  });

  assert.deepEqual(
    page.data.faceTurns.map(({ responseId, src, tgt }) => ({ responseId, src, tgt })),
    [
      { responseId: 'r1', src: '第一句', tgt: 'Câu một' },
      { responseId: 'r2', src: '第二句', tgt: 'Câu hai' }
    ]
  );
});

module.exports = { loadPage, completeTextResponse };
