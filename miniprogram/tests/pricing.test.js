const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

test('shows processing instead of payment failure while fulfillment is pending', async () => {
  const apiPath = path.resolve(__dirname, '../utils/api.js');
  const payPath = path.resolve(__dirname, '../utils/pay.js');
  const pricingPath = path.resolve(__dirname, '../pages/pricing/pricing.js');
  require.cache[apiPath] = { exports: { request: async () => [] } };
  require.cache[payPath] = {
    exports: { payPlan: async () => ({ success: false, processing: true }) },
  };
  global.getApp = () => ({ globalData: { freeGrantMinutes: 30 } });
  const toasts = [];
  global.wx = { showToast: (value) => toasts.push(value), switchTab() {} };
  let page;
  global.Page = (value) => { page = value; };
  delete require.cache[pricingPath];
  require(pricingPath);

  await page.onBuy({ currentTarget: { dataset: { plan: 'pack_small' } } });

  assert.equal(toasts.length, 1);
  assert.equal(toasts[0].title, '支付处理中，请稍后查看套餐');
});
