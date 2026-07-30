// utils/pay.js — 小程序内微信支付封装（虚拟支付 / 道具直购）
// 统一封装「wx.login 拿 code → 下单 → wx.requestVirtualPayment → 结果处理」，
// 供 pricing 等页面复用。
//
// 注意：时长包是虚拟商品，按微信平台规则只能走虚拟支付
// （wx.requestVirtualPayment），不能再用 wx.requestPayment。
const { request } = require('./api.js');
const app = getApp();

async function pollOrderStatus(outTradeNo, options = {}) {
  const maxAttempts = options.maxAttempts || 12;
  const delayMs = options.delayMs === undefined ? 1000 : options.delayMs;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const status = await request(
      'GET',
      '/billing/order_status',
      { out_trade_no: outTradeNo },
      true
    );
    if (status && status.paid) return { success: true };
    if (delayMs && attempt < maxAttempts - 1) {
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
  return { success: false, processing: true };
}

/**
 * 拉起小程序微信虚拟支付购买指定套餐。
 * @param {string} planId 时长包 id（如 pack_medium）
 * @returns {Promise<{success:boolean, cancelled?:boolean, errMsg?:string}>}
 */
function payPlan(planId) {
  return new Promise((resolve) => {
    if (!planId) {
      resolve({ success: false, errMsg: '套餐参数缺失' });
      return;
    }
    wx.showLoading({ title: '下单中', mask: true });

    // /billing/create_order 需要 Bearer token；先确保 app.login() 完成拿到 JWT，
    // 避免和 onLaunch 登录竞态导致 401 看似「支付按钮无反应」。
    app.login().catch(() => null).then(() => {
      // virtualpay 的 signature 依赖用户的 session_key，每次下单前都重新
      // wx.login 拿一个新鲜的 code，由后端 jscode2session 换 session_key。
      new Promise((res, rej) => {
        wx.login({
          success: (r) => (r && r.code ? res(r.code) : rej(new Error('wx.login 未返回 code'))),
          fail: rej,
        });
      })
        .then((code) =>
          request(
            'POST',
            '/billing/create_order',
            { plan_id: planId, pay_type: 'virtualpay', wx_code: code },
            true
          )
        )
        .then((res) => {
          wx.hideLoading();
          if (res && res.pay_type === 'virtualpay' && res.payment_params) {
            const p = res.payment_params;
            // signData / paySig / signature / offerId / mode / env 必须
            // 原样传过去，不能改字段顺序也不能多加字段（否则 -15005）。
            wx.requestVirtualPayment({
              mode: p.mode,                  // 'short_series_goods'
              env: p.env,                    // 0=现网, 1=沙箱
              offerId: p.offerId,            // 虚拟支付商户号
              paySig: p.paySig,
              signData: p.signData,          // 后端生成的 JSON 字符串
              signature: p.signature,
              success: () => {
                pollOrderStatus(res.out_trade_no)
                  .then(resolve)
                  .catch((err) => resolve({
                    success: false,
                    processing: true,
                    errMsg: (err && err.message) || '支付结果确认中',
                  }));
              },
              fail: (err) => {
                // 保留完整错误对象，便于真机调试时拿到 errCode / errMsg，
                // 避免只显示截断后的“requestvirtualpayment:fail”。
                console.error('[vpay-fail]', JSON.stringify(err));
                const msg = (err && err.errMsg) || '';
                // 用户主动取消：errMsg 含 'cancel'
                if (msg.indexOf('cancel') !== -1) {
                  resolve({ success: false, cancelled: true });
                } else {
                  const code = err && (err.errCode !== undefined ? err.errCode : err.err_code);
                  const detail = code !== undefined ? `${msg || '支付未完成'} (errCode: ${code})` : (msg || '支付未完成');
                  resolve({ success: false, cancelled: false, errMsg: detail });
                }
              },
            });
          } else {
            resolve({ success: false, errMsg: (res && res.detail) || '下单失败' });
          }
        })
        .catch((err) => {
          wx.hideLoading();
          resolve({ success: false, errMsg: (err && err.message) || '下单失败' });
        });
    });
  });
}

module.exports = { payPlan, pollOrderStatus };
