const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

function loadPage() {
  let config;
  let stopCount = 0;
  let playCount = 0;
  let toastCount = 0;
  const audios = [];

  function createAudio() {
    const audio = {
      src: '',
      obeyMuteSwitch: true,
      stop() { stopCount += 1; },
      play() { playCount += 1; },
      destroy() {},
      onPlay(callback) { this.handlePlay = callback; },
      onEnded(callback) { this.handleEnded = callback; },
      onStop(callback) { this.handleStop = callback; },
      onError(callback) { this.handleError = callback; }
    };
    audios.push(audio);
    return audio;
  }

  global.wx = {
    createInnerAudioContext: createAudio,
    showToast() { toastCount += 1; }
  };
  global.Page = (value) => { config = value; };

  const pagePath = path.resolve(__dirname, '../pages/messages/messages.js');
  delete require.cache[pagePath];
  require(pagePath);

  const page = { ...config, data: { ...config.data } };
  page.setData = (next, callback) => {
    Object.assign(page.data, next);
    if (callback) callback();
  };
  page.onLoad();

  return {
    page,
    audios,
    stopCount: () => stopCount,
    playCount: () => playCount,
    toastCount: () => toastCount
  };
}

test('first phrase playback does not stop an empty iOS audio context', () => {
  const { page, audios, stopCount, playCount } = loadPage();

  page.playPhrase({ currentTarget: { dataset: { id: 'shopping-1', lang: 'vi' } } });

  assert.equal(stopCount(), 0);
  assert.equal(playCount(), 1);
  assert.equal(page.data.playingKey, 'shopping-1-vi');
  assert.match(audios[0].src, /shopping-1-vi\.wav$/);
});

test('switching phrases still stops the active playback before starting another', () => {
  const { page, audios, stopCount, playCount } = loadPage();

  page.playPhrase({ currentTarget: { dataset: { id: 'shopping-1', lang: 'vi' } } });
  page.playPhrase({ currentTarget: { dataset: { id: 'shopping-2', lang: 'zh' } } });

  assert.equal(stopCount(), 1);
  assert.equal(playCount(), 2);
  assert.equal(page.data.playingKey, 'shopping-2-zh');
  assert.match(audios[1].src, /shopping-2-zh\.mp3$/);
});

test('late callbacks from a replaced phrase cannot clear or error the new playback', () => {
  const { page, audios, toastCount } = loadPage();

  page.playPhrase({ currentTarget: { dataset: { id: 'shopping-1', lang: 'vi' } } });
  const oldAudio = audios[0];
  page.playPhrase({ currentTarget: { dataset: { id: 'shopping-2', lang: 'zh' } } });

  oldAudio.handleStop();
  oldAudio.handleError();

  assert.equal(page.data.playingKey, 'shopping-2-zh');
  assert.equal(page.data.audioLoading, true);
  assert.equal(toastCount(), 0);
});
