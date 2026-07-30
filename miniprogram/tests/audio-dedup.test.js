const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

function loadPage() {
  const stubs = {
    '../utils/recorder.js': { RecorderManager: class {} },
    '../utils/live.js': { LiveTranslate: class {} },
    '../utils/api.js': { request: async () => ({}) },
    '../utils/session.js': { ensureSession() {} },
  };
  for (const [relative, exports] of Object.entries(stubs)) {
    const modulePath = path.resolve(__dirname, relative);
    require.cache[modulePath] = { exports };
  }

  global.getApp = () => ({ updateQuota() {} });
  let config;
  global.Page = (value) => { config = value; };
  const pagePath = path.resolve(__dirname, '../pages/index/index.js');
  delete require.cache[pagePath];
  require(pagePath);
  const page = { ...config, data: { ...config.data } };
  page.setData = (next) => Object.assign(page.data, next);
  page.sourceItemIndexes = Object.create(null);
  page.translationResponseIndexes = Object.create(null);
  return page;
}

test('suppresses microphone upload while translated audio is playing', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/index/index.js'), 'utf8');
  const handler = source.match(/this\.recorder\.onFrame = \(frame\) => \{([\s\S]*?)\n    \};/);

  assert.ok(handler, 'recorder frame handler should exist');
  assert.match(handler[1], /ttsPlaying/);
  assert.match(handler[1], /return/);
  assert.match(handler[1], /sendAudioFrame\(frame\)/);
});

test('defaults live source to Chinese instead of auto-detect', () => {
  const page = loadPage();
  assert.equal(page.data.sourceLangs[page.data.sourceIndex].code, 'zh');
  assert.equal(page.data.targetLangs[page.data.targetIndex].code, 'vi');
});

test('reconnects an interrupted upstream without stopping the recorder', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/index/index.js'), 'utf8');
  const handler = source.match(/handleVoiceDisconnect\(live, err\) \{([\s\S]*?)\n  \},/);

  assert.ok(handler, 'disconnect handler should exist');
  assert.match(handler[1], /openVoiceConnection\(\)/);
  assert.doesNotMatch(handler[1], /stopSession\(/);
});

test('plays streaming PCM and suppresses the duplicate complete WAV', () => {
  const page = loadPage();
  const queued = [];
  page.data.running = true;
  page.playStreamingPcm = () => { queued.push('pcm'); return true; };
  page.enqueueAudio = (audio, force) => queued.push({ audio, force });
  page.setData = () => {};

  page.handleLiveMessage({ type: 'model_event', response_started: true });
  page.handleLiveMessage({ type: 'model_audio', audio: 'pcm' });
  page.handleLiveMessage({ type: 'model_audio_wav', audio: 'wav' });

  assert.deepEqual(queued, ['pcm']);
});

test('keeps earlier source items visible when a new transcription item starts', () => {
  const page = loadPage();
  page.updateDraft('source', '第一句', 'item-1');
  page.updateDraft('source', '第二句', 'item-2');
  assert.deepEqual(page.sourceHistory, ['第一句']);
  assert.equal(page.sourceDraft, '第二句');
  page.commitFinal('source', '第一句。', 'item-1');
  assert.deepEqual(page.sourceHistory, ['第一句。']);
  assert.equal(page.sourceDraft, '第二句');
});

test('keeps every source sentence when realtime events omit item ids', () => {
  const page = loadPage();
  page.data.running = true;

  page.handleLiveMessage({ type: 'model_event', source_partial: '第一句原文' });
  page.handleLiveMessage({ type: 'model_event', response_started: true, response_id: 'r1' });
  page.handleLiveMessage({ type: 'model_event', source_partial: '第二句原文' });
  page.handleLiveMessage({ type: 'model_event', response_started: true, response_id: 'r2' });
  page.handleLiveMessage({ type: 'model_event', source_partial: '第三句原文' });

  assert.deepEqual(page.data.sourceLines, ['第一句原文', '第二句原文']);
  assert.equal(page.data.sourceDraft, '第三句原文');
});

test('stopping voice mode preserves committed and current source text', () => {
  const page = loadPage();
  page.data.running = true;
  page.live = { close() {} };
  page.recorder = { stop() {} };
  page.stopAudioPlayback = () => {};
  page.handleLiveMessage({ type: 'model_event', source_partial: '第一句原文' });
  page.handleLiveMessage({ type: 'model_event', response_started: true, response_id: 'r1' });
  page.handleLiveMessage({ type: 'model_event', source_partial: '最后一句原文' });

  page.stopSession();

  assert.deepEqual(page.data.sourceLines, ['第一句原文']);
  assert.equal(page.data.sourceDraft, '最后一句原文');
});

test('keeps source sentences when no-id partial text resets without a response boundary', () => {
  const page = loadPage();

  page.updateDraft('source', '第一句原文');
  page.updateDraft('source', '第二句原文');
  page.updateDraft('source', '第三句原文');

  assert.deepEqual(page.data.sourceLines, ['第一句原文', '第二句原文']);
  assert.equal(page.data.sourceDraft, '第三句原文');
});

test('keeps cumulative and tail-corrected source partials in one draft', () => {
  const page = loadPage();

  page.updateDraft('source', '今天去');
  page.updateDraft('source', '今天去北京');
  page.updateDraft('source', '今天去北海');

  assert.deepEqual(page.data.sourceLines, []);
  assert.equal(page.data.sourceDraft, '今天去北海');
});

test('source and translation panels advance their scroll positions on every update', () => {
  const page = loadPage();
  page.updateDraft('source', '实时原文');
  const firstSourceScroll = page.data.sourceScrollTop;
  page.updateDraft('source', '实时原文继续');
  assert.ok(page.data.sourceScrollTop > firstSourceScroll);

  page.updateDraft('translation', 'Bản dịch trực tiếp', 'r1');
  const firstTranslationScroll = page.data.translationScrollTop;
  page.updateDraft('translation', 'Bản dịch tiếp tục', 'r1');
  assert.ok(page.data.translationScrollTop > firstTranslationScroll);
});

test('does not mistake two sentences with a short shared prefix for one revision', () => {
  const page = loadPage();

  page.updateDraft('source', '你好世界');
  page.updateDraft('source', '你好朋友');

  assert.deepEqual(page.data.sourceLines, ['你好世界']);
  assert.equal(page.data.sourceDraft, '你好朋友');
});

test('a delayed duplicate no-id source final does not clear the next sentence', () => {
  const page = loadPage();

  page.updateDraft('source', 'first source sentence');
  page.commitFinal('source', 'first source sentence');
  page.updateDraft('source', 'second source sentence');
  page.commitFinal('source', 'first source sentence');

  assert.deepEqual(page.data.sourceLines, ['first source sentence']);
  assert.equal(page.data.sourceDraft, 'second source sentence');
});

test('a delayed distinct no-id source final does not clear a newer draft', () => {
  const page = loadPage();

  page.updateDraft('source', 'new visible sentence');
  page.commitFinal('source', 'late previous final');

  assert.deepEqual(page.data.sourceLines, ['late previous final']);
  assert.equal(page.data.sourceDraft, 'new visible sentence');
});

test('voice templates bind both realtime panels to independent scroll positions', () => {
  const template = fs.readFileSync(path.resolve(__dirname, '../pages/index/index.wxml'), 'utf8');
  const styles = fs.readFileSync(path.resolve(__dirname, '../pages/index/index.wxss'), 'utf8');
  assert.match(template, /scroll-top="{{sourceScrollTop}}"/);
  assert.match(template, /scroll-top="{{translationScrollTop}}"/);
  assert.match(styles, /\.voice-workspace \.voice-panel\s*{[^}]*height:\s*420rpx/s);
});

test('auto-plays the complete WAV when streaming audio is unavailable', () => {
  const page = loadPage();
  const queued = [];
  page.data.running = true;
  page.enqueueAudio = (audio, force) => queued.push({ audio, force });

  page.handleLiveMessage({ type: 'model_audio_wav', audio: 'wav' });

  assert.deepEqual(queued, [{ audio: 'wav', force: undefined }]);
});

test('ignores audio after session fully stopped', () => {
  const page = loadPage();
  const queued = [];
  page.data.running = false;
  page.finishingLive = null;
  page.enqueueAudio = (audio) => queued.push(audio);

  page.handleLiveMessage({ type: 'model_audio_wav', audio: 'late' });

  assert.deepEqual(queued, []);
});

test('ignores final complete WAV after immediate voice stop', () => {
  const page = loadPage();
  const queued = [];
  page.data.running = false;
  page.finishingLive = {};
  page.enqueueAudio = (audio) => queued.push(audio);

  page.handleLiveMessage({ type: 'model_audio_wav', audio: 'tail' });

  assert.deepEqual(queued, []);
});

test('voice stop closes immediately without requesting graceful finish', () => {
  const page = loadPage();
  const calls = [];
  page.data.running = true;
  page.live = {
    close() { calls.push('close'); },
    finish() { calls.push('finish'); }
  };
  page.recorder = { stop() { calls.push('recorder.stop'); } };
  page.stopAudioPlayback = () => calls.push('audio.stop');

  page.stopSession();

  assert.deepEqual(calls, ['close', 'recorder.stop', 'audio.stop']);
  assert.equal(page.data.running, false);
  assert.equal(page.data.statusText, '已停止');
});

test('recorder prefers the voice communication audio source for system AEC', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../utils/recorder.js'), 'utf8');
  assert.match(source, /getAvailableAudioSources/);
  assert.match(source, /voice_communication/);
  assert.match(source, /audioSource: this\.audioSource/);
});

test('face mode ignores PCM and queues one complete WAV for its turn', () => {
  const page = loadPage();
  const queued = [];
  page.data.faceSide = 'mine';
  page.enqueuePcmAudio = () => queued.push('pcm');
  page.handleCompleteAudio = () => queued.push('legacy');
  page.queueFaceTurnAudio = (turnId) => queued.push(turnId);

  page.handleFaceMessage({ type: 'model_event', source_final: '你好' });
  page.handleFaceMessage({ type: 'model_event', response_started: true, response_id: 'r1' });
  page.handleFaceMessage({ type: 'model_event', translation_final: 'Xin chào', response_id: 'r1' });
  page.handleFaceMessage({ type: 'model_event', response_done: true, response_id: 'r1' });
  const turnId = page.data.faceTurns[0].id;
  page.handleFaceMessage({ type: 'model_audio', audio: 'pcm', response_id: 'r1' });
  page.handleFaceMessage({ type: 'model_audio_wav', audio: 'wav', response_id: 'r1' });
  page.handleFaceMessage({ type: 'model_audio_wav', audio: 'wav', response_id: 'r1' });

  assert.deepEqual(queued, [turnId]);
});

test('face queues complete WAV without response_done when translation arrives first', () => {
  const page = loadPage();
  const queued = [];
  page.queueFaceTurnAudio = (turnId, audio) => queued.push({ turnId, audio });

  page.handleFaceMessage({ type: 'model_event', response_started: true, response_id: 'r1' });
  page.handleFaceMessage({
    type: 'model_event',
    translation_final: 'Xin chào',
    response_id: 'r1'
  });
  page.handleFaceMessage({ type: 'model_audio_wav', audio: 'wav1', response_id: 'r1' });

  assert.deepEqual(queued, [{ turnId: page.data.faceTurns[0].id, audio: 'wav1' }]);
});

test('face queues complete WAV once when audio arrives before translation', () => {
  const page = loadPage();
  const queued = [];
  page.queueFaceTurnAudio = (turnId, audio) => queued.push({ turnId, audio });

  page.handleFaceMessage({ type: 'model_event', response_started: true, response_id: 'r2' });
  page.handleFaceMessage({ type: 'model_audio_wav', audio: 'wav2', response_id: 'r2' });
  page.handleFaceMessage({
    type: 'model_event',
    translation_final: 'Chào bạn',
    response_id: 'r2'
  });
  page.handleFaceMessage({ type: 'model_event', response_done: true, response_id: 'r2' });

  assert.equal(queued.length, 1);
  assert.equal(queued[0].audio, 'wav2');
});

test('audio queue unwraps turn items and continues after an error', () => {
  const page = loadPage();
  const contexts = [];
  const deleted = [];
  const originalSetTimeout = global.setTimeout;
  const originalWarn = console.warn;
  global.setTimeout = () => 1;
  console.warn = () => {};
  global.wx = {
    createInnerAudioContext() {
      const context = {
        src: '',
        duration: 0,
        currentTime: 0,
        destroy() {},
        play() {},
        onEnded(callback) { this.ended = callback; },
        onError(callback) { this.error = callback; },
        onTimeUpdate() {}
      };
      contexts.push(context);
      return context;
    },
    getFileSystemManager() {
      return { unlink({ filePath }) { deleted.push(filePath); } };
    }
  };
  try {
    page.audioQueue = [
      { path: 'first.wav', turnId: 'turn-1' },
      { path: 'second.wav', turnId: 'turn-2' }
    ];

    page.playNextAudio();
    contexts[0].error(new Error('decode failed'));

    assert.equal(contexts.length, 2);
    assert.equal(contexts[0].src, 'first.wav');
    assert.equal(contexts[1].src, 'second.wav');
    assert.deepEqual(deleted, ['first.wav']);
  } finally {
    global.setTimeout = originalSetTimeout;
    console.warn = originalWarn;
  }
});
