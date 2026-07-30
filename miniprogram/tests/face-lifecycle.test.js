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
  global.getApp = () => ({ updateQuota() {} });
  global.wx = { showToast() {}, vibrateShort() {} };
  let config;
  global.Page = (value) => { config = value; };
  const pagePath = path.resolve(__dirname, '../pages/index/index.js');
  delete require.cache[pagePath];
  require(pagePath);
  const page = { ...config, data: { ...config.data } };
  page.setData = (next) => Object.assign(page.data, next);
  return page;
}

test('face mic release waits for session_finished and preserves turns', () => {
  const page = loadPage();
  const calls = [];
  const originalSetTimeout = global.setTimeout;
  const originalClearTimeout = global.clearTimeout;
  global.setTimeout = () => 1;
  global.clearTimeout = () => {};
  try {
    page.recorder = { stop() { calls.push('recorder.stop'); } };
    page.live = {
      finish() { calls.push('live.finish'); },
      stop() { calls.push('live.stop'); },
      close() { calls.push('live.close'); }
    };
    page.data.faceRecording = true;
    page.data.faceTurns = [{ side: 'mine', src: '你好', tgt: 'Xin chào' }];

    page.stopFaceMic();

    assert.deepEqual(calls, ['recorder.stop', 'live.finish']);
    assert.equal(page.data.faceFinalizing, true);
    assert.equal(page.live, null);
    assert.deepEqual(page.data.faceTurns, [
      { side: 'mine', src: '你好', tgt: 'Xin chào' }
    ]);

    page.handleFaceMessage({ type: 'model_event', session_finished: true });
    assert.equal(page.data.faceFinalizing, false);
    assert.equal(calls.includes('live.close'), true);
  } finally {
    global.setTimeout = originalSetTimeout;
    global.clearTimeout = originalClearTimeout;
  }
});

test('face mic press is blocked while the previous turn is finalizing', () => {
  const page = loadPage();
  let starts = 0;
  page.data.faceFinalizing = true;
  page.startFaceMic = () => { starts += 1; };

  page.onFaceMicDown({ currentTarget: { dataset: { side: 'mine' } } });

  assert.equal(starts, 0);
});

test('face finalizing timeout closes the socket and unlocks the next turn', () => {
  const page = loadPage();
  let timeoutCallback;
  let timeoutDelay;
  let closes = 0;
  const originalSetTimeout = global.setTimeout;
  const originalClearTimeout = global.clearTimeout;
  global.setTimeout = (callback, delay) => {
    timeoutCallback = callback;
    timeoutDelay = delay;
    return 1;
  };
  global.clearTimeout = () => {};
  try {
    page.recorder = { stop() {} };
    page.live = {
      finish() {},
      close() { closes += 1; }
    };
    page.data.faceRecording = true;

    page.stopFaceMic();

    assert.equal(timeoutDelay, 15000);
    timeoutCallback();
    assert.equal(closes, 1);
    assert.equal(page.data.faceFinalizing, false);
    assert.equal(page.data.statusText, '本轮处理超时');
  } finally {
    global.setTimeout = originalSetTimeout;
    global.clearTimeout = originalClearTimeout;
  }
});

test('switching modes does not clear completed face turns', () => {
  const page = loadPage();
  page.data.faceTurns = [{ side: 'mine', src: 'Hello', tgt: '你好' }];

  page.onSetMode({ currentTarget: { dataset: { mode: 'photo' } } });
  page.onSetMode({ currentTarget: { dataset: { mode: 'face' } } });

  assert.deepEqual(page.data.faceTurns, [
    { side: 'mine', src: 'Hello', tgt: '你好' }
  ]);
});

test('finish failure closes immediately instead of waiting for timeout', () => {
  const page = loadPage();
  let closed = 0;
  page.recorder = { stop() {} };
  page.live = {
    finish() { return false; },
    close() { closed += 1; }
  };
  page.data.faceRecording = true;

  page.stopFaceMic();

  assert.equal(closed, 1);
  assert.equal(page.data.faceFinalizing, false);
  assert.equal(page.finishingLive, null);
});

test('face recorder error invalidates callbacks from the old generation', () => {
  const page = loadPage();
  const oldGeneration = 4;
  let closed = 0;
  page.faceGen = oldGeneration;
  page.data.faceRecording = true;
  page.live = {
    close() { closed += 1; }
  };
  page.recorder = { stop() {} };

  page.stopFaceMic('录音失败');

  assert.equal(page.faceGen, oldGeneration + 1);
  assert.equal(closed, 1);
  assert.equal(page.data.faceRecording, false);
});
