// pages/pricing/pricing.js
const app = getApp();
const { request } = require('../../utils/api.js');
const { payPlan } = require('../../utils/pay.js');

// 兜底套餐（后端未就绪时也能正常展示）——分钟数存放于 chars_per_period
const FALLBACK_PLANS = [
  { id: 'pack_small', name: '小包', price_cents: 990, chars_per_period: 60, interval: 'payg' },
  { id: 'pack_medium', name: '中包', price_cents: 1990, chars_per_period: 200, interval: 'payg' },
  { id: 'pack_large', name: '大包', price_cents: 4990, chars_per_period: 600, interval: 'payg' }
];

// 每档亮点标签
const HIGHLIGHT = {
  pack_small: '轻度尝鲜',
  pack_medium: '最划算',
  pack_large: '重度首选'
};

Page({
  data: {
    packs: [],
    loading: true,
    freeMinutes: 30
  },

  onShow() {
    this.loadPlans();
    this.refreshFree();
  },

  // 拉取后端套餐（公开接口，无需登录），失败则用兜底数据
  async loadPlans() {
    this.setData({ loading: true });
    let list = FALLBACK_PLANS;
    try {
      const plans = await request('GET', '/billing/plans', {}, false);
      if (Array.isArray(plans) && plans.length) {
        list = plans.filter((p) => p.interval === 'payg' && p.price_cents > 0);
        if (!list.length) list = FALLBACK_PLANS;
      }
    } catch (e) {
      // 网络异常，保留兜底
    }
    const packs = list
      .map((p) => {
        const minutes = p.chars_per_period || 0;
        const yuan = p.price_cents / 100;
        return {
          id: p.id || p.code,
          code: p.code || p.id,
          name: p.name,
          minutes,
          priceYuan: yuan.toFixed(2).replace(/\.00$/, ''),
          perMin: minutes ? (yuan / minutes).toFixed(3).replace(/0+$/, '').replace(/\.$/, '') : '-',
          recommend: (p.code || p.id) === 'pack_medium',
          highlight: HIGHLIGHT[p.code || p.id] || '按量购买'
        };
      })
      .sort((a, b) => a.minutes - b.minutes);
    this.setData({ packs, loading: false });
  },

  // 免费总额（分钟）
  refreshFree() {
    const q = app.globalData.freeQuota || { used: 0, limit: 1800 };
    this.setData({
      freeMinutes: Math.round((q.limit || 1800) / 60)
    });
  },

  async onBuy(e) {
    const planId = e.currentTarget.dataset.plan;
    const r = await payPlan(planId);
    if (r.processing) {
      wx.showToast({
        title: '支付处理中，请稍后查看套餐',
        icon: 'none',
        duration: 3000
      });
    } else if (r.success) {
      wx.showToast({ title: '购买成功', icon: 'success' });
      this.loadPlans();
    } else if (!r.cancelled) {
      wx.showToast({ title: r.errMsg || '支付未完成', icon: 'none' });
    }
  },

  onBackHome() {
    wx.switchTab({ url: '/pages/index/index' });
  }
});
