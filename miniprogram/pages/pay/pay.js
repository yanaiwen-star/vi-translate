// pages/pay/pay.js
// 由网页端小程序码（checkout.html 生成的 pages/pay/pay?scene=<out_trade_no>）
// 或普通跳转（pages/pay/pay?out_trade_no=xxx）打开。拉起小程序微信虚拟支付完成付款。
//
// 走的是「道具直购」流程：wx.login 拿 code → /billing/mini_pay 下单
// → wx.requestVirtualPayment 拉起支付。支付成功的发货以微信推送为准
// （xpay_goods_deliver_notify 回调到后端 /billing/virtualpay/notify），
// success 回调只是触发轮询 /billing/order_status 的信号，并不等于分钟已到账。
const app = getApp();
const { request } = require('../../utils/api.js');

Page({
  data: {
    loading: true,
    paying: false,
    done: false,
    error: ''
  },

  onLoad(query) {
    this._pageActive = true;
    this._timers = [];
    const q = query || {};
    const otn = q.out_trade_no || q.scene || '';
    if (!otn) {
      this.setData({ loading: false, error: '缺少订单参数' });
      return;
    }
    this.setData({ outTradeNo: otn });
    // 确保小程序已登录（拿到 JWT），下单接口依赖 JWT
    app.login().catch(() => {}).then(() => {
      if (this._pageActive) this.startPay();
    });
  },

  onShow() {
    this._pageActive = true;
  },

  onHide() {
    this._pageActive = false;
    this.clearTimers();
  },

  onUnload() {
    this._pageActive = false;
    this.clearTimers();
  },

  clearTimers() {
    (this._timers || []).forEach((timer) => clearTimeout(timer));
    this._timers = [];
  },

  schedule(callback, delay) {
    if (!this._pageActive) return null;
    const timer = setTimeout(() => {
      this._timers = (this._timers || []).filter((item) => item !== timer);
      if (this._pageActive) callback();
    }, delay);
    this._timers.push(timer);
    return timer;
  },

  startPay() {
    if (!this._pageActive || this.data.paying || this.data.done) return;
    this.setData({ paying: true, loading: false, error: '' });

    // 先 wx.login 拿 code，后端用这个 code 换 session_key 算 signature
    new Promise((res, rej) => {
      wx.login({
        success: (r) => (r && r.code ? res(r.code) : rej(new Error('wx.login 未返回 code'))),
        fail: rej,
      });
    })
      .then((code) =>
        request(
          'POST',
          '/billing/mini_pay',
          {
            out_trade_no: this.data.outTradeNo,
            pay_type: 'virtualpay',
            wx_code: code,
          },
          true
        )
      )
      .then((res) => {
        if (!this._pageActive) return;
        if (res && res.paid) {
          this.setData({ done: true, paying: false });
          wx.showToast({ title: '订单已支付', icon: 'success' });
          // 支付成功跳回个人中心，确认分钟数到账
          this.schedule(() => wx.switchTab({ url: '/pages/profile/profile' }), 1200);
          return;
        }
        if (res && res.pay_type === 'virtualpay' && res.payment_params) {
          const p = res.payment_params;
          wx.requestVirtualPayment({
            mode: p.mode,
            env: p.env,
            offerId: p.offerId,
            paySig: p.paySig,
            signData: p.signData,
            signature: p.signature,
            success: () => {
              // success 回调只是「用户已付」，实际分钟到账以微信推送为准。
              // 这里不直接 setData done，等下面轮询到 order_status=paid 再翻页。
              this.startPolling();
            },
            fail: (err) => this.onPayFail(err),
          });
        } else {
          this.setData({ paying: false, error: (res && res.detail) || '下单失败' });
        }
      })
      .catch((err) => {
        if (!this._pageActive) return;
        this.setData({ paying: false, error: (err && err.message) || '下单失败' });
      });
  },

  // 支付 success 后轮询 /billing/order_status，等到 paid 才算真正到账
  startPolling() {
    const otn = this.data.outTradeNo;
    let tries = 0;
    const max = 10;
    const tick = () => {
      if (!this._pageActive) return;
      request('GET', '/billing/order_status', { out_trade_no: otn }, true)
        .then((s) => {
          if (!this._pageActive) return;
          if (s && s.paid) {
            this.setData({ done: true, paying: false });
            wx.showToast({ title: '支付成功', icon: 'success' });
            // 支付成功跳回个人中心，确认分钟数到账
            this.schedule(() => wx.switchTab({ url: '/pages/profile/profile' }), 1200);
            return;
          }
          if (++tries >= max) {
            this.setData({ paying: false, error: '处理中，请稍后下拉刷新' });
            return;
          }
          this.schedule(tick, 1500);
        })
        .catch(() => {
          if (!this._pageActive) return;
          if (++tries >= max) {
            this.setData({ paying: false, error: '处理中，请稍后下拉刷新' });
            return;
          }
          this.schedule(tick, 1500);
        });
    };
    tick();
  },

  onPayFail(err) {
    const msg = (err && err.errMsg) || '';
    this.setData({ paying: false });
    if (msg.indexOf('cancel') !== -1) {
      this.setData({ error: '已取消支付' });
    } else {
      this.setData({ error: '支付未完成，请重试' });
    }
  },

  onRetry() {
    this.startPay();
  },

  onBackHome() {
    wx.switchTab({ url: '/pages/index/index' });
  }
});
