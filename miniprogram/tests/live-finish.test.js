const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const { LiveTranslate } = require(path.resolve(__dirname, '../utils/live.js'));

test('finish requests graceful session completion without closing the socket', () => {
  const sent = [];
  let closed = false;
  const live = new LiveTranslate();
  live.connected = true;
  live.task = {
    send(message) { sent.push(JSON.parse(message.data)); },
    close() { closed = true; }
  };

  assert.equal(live.finish(), true);

  assert.deepEqual(sent, [{ type: 'finish' }]);
  assert.equal(closed, false);
});

test('finish returns false when the socket is unavailable', () => {
  const live = new LiveTranslate();

  assert.equal(live.finish(), false);

  live.connected = true;
  live.task = {
    send() { throw new Error('socket closed'); }
  };
  assert.equal(live.finish(), false);
});
