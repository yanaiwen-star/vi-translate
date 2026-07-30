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

test('face panels bind scrolling and highlighting to stable turn ids', () => {
  const wxml = fs.readFileSync(
    path.resolve(__dirname, '../pages/index/index.wxml'),
    'utf8'
  );

  assert.match(wxml, /scroll-into-view="\{\{faceTopScrollTarget\}\}"/);
  assert.match(wxml, /scroll-into-view="\{\{faceBottomScrollTarget\}\}"/);
  assert.match(wxml, /id="face-top-\{\{item\.id\}\}"/);
  assert.match(wxml, /id="face-bottom-\{\{item\.id\}\}"/);
  assert.match(wxml, /facePlayingTurnId === item\.id/);
});

test('text updates focus the matching turn in both panels', () => {
  const page = loadPage();
  page.data.faceSide = 'mine';
  page.handleFaceMessage({ type: 'model_event', response_started: true, response_id: 'r1' });
  const turnId = page.data.faceTurns[0].id;

  page.handleFaceMessage({
    type: 'model_event',
    translation_partial: 'Xin chào',
    response_id: 'r1'
  });

  assert.equal(page.data.faceTopScrollTarget, `face-top-${turnId}`);
  assert.equal(page.data.faceBottomScrollTarget, `face-bottom-${turnId}`);
});

test('playback highlights its turn and clears highlight when finished', () => {
  const page = loadPage();
  let ended;
  const originalSetTimeout = global.setTimeout;
  global.setTimeout = () => 1;
  global.wx = {
    createInnerAudioContext() {
      return {
        src: '',
        duration: 0,
        currentTime: 0,
        destroy() {},
        play() {},
        onEnded(callback) { ended = callback; },
        onError() {},
        onTimeUpdate() {}
      };
    },
    getFileSystemManager() {
      return { unlink() {} };
    }
  };
  try {
    page.audioQueue = [{ path: 'sentence.wav', turnId: 'turn-9' }];
    page.playNextAudio();

    assert.equal(page.data.facePlayingTurnId, 'turn-9');
    assert.equal(page.data.faceTopScrollTarget, 'face-top-turn-9');
    assert.equal(page.data.faceBottomScrollTarget, 'face-bottom-turn-9');

    ended();
    assert.equal(page.data.facePlayingTurnId, '');
  } finally {
    global.setTimeout = originalSetTimeout;
  }
});

test('clear removes face text, pending audio and playback highlight', () => {
  const page = loadPage();
  let destroyed = 0;
  page.data.faceTurns = [{ id: 'turn-1', src: '你好', tgt: 'Xin chào' }];
  page.data.facePlayingTurnId = 'turn-1';
  page.data.faceTopScrollTarget = 'face-top-turn-1';
  page.data.faceBottomScrollTarget = 'face-bottom-turn-1';
  page.audioQueue = [{ path: 'pending.wav', turnId: 'turn-2' }];
  page.playingAudio = { destroy() { destroyed += 1; } };

  page.onFaceClear();

  assert.equal(destroyed, 1);
  assert.deepEqual(page.audioQueue, []);
  assert.deepEqual(page.data.faceTurns, []);
  assert.equal(page.data.facePlayingTurnId, '');
  assert.equal(page.data.faceTopScrollTarget, '');
  assert.equal(page.data.faceBottomScrollTarget, '');
});
