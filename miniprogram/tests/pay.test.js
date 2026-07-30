const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

function loadPay(request) {
  const apiPath = path.resolve(__dirname, '../utils/api.js');
  const payPath = path.resolve(__dirname, '../utils/pay.js');
  require.cache[apiPath] = { exports: { request } };
  global.getApp = () => ({ login: async () => ({}) });
  delete require.cache[payPath];
  return require(payPath);
}

test('polls until backend reports paid', async () => {
  let calls = 0;
  const { pollOrderStatus } = loadPay(async () => ({ paid: ++calls === 2 }));
  const result = await pollOrderStatus('otn', { maxAttempts: 2, delayMs: 0 });
  assert.deepEqual(result, { success: true });
  assert.equal(calls, 2);
});

test('returns processing when backend stays pending', async () => {
  const { pollOrderStatus } = loadPay(async () => ({ paid: false }));
  const result = await pollOrderStatus('otn', { maxAttempts: 2, delayMs: 0 });
  assert.deepEqual(result, { success: false, processing: true });
});
