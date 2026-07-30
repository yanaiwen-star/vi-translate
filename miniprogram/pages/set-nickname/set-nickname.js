// pages/set-nickname/set-nickname.js
// 强制设置昵称页：用户首次发起同传/被后端 NICKNAME_REQUIRED 拦截时跳到此页。
// 保存成功后通过 getCurrentPages()/navigateBack 回上一页面，运营可在后台立即看到。
const app = getApp();
const { request } = require('../../utils/api.js');

Page({
  data: {
    draft: '',
    saving: false,
    reason: '',     // 来自 navigateTo query 的可选原因
    allowBack: true // 来源：「我的」主动改昵称时可以返回
  },

  onLoad(query) {
    // 来源：「我的」主动改昵称 vs 后端拦截强制
    this.setData({
      reason: (query && query.reason) || '',
      allowBack: !!(query && query.from === 'profile')
    });
    // 预填已有昵称
    if (app.globalData.nickname) {
      this.setData({ draft: app.globalData.nickname });
    }
  },

  onInput(e) {
    this.setData({ draft: e.detail.value });
  },

  // 微信键盘"使用微信昵称"回填
  onWechatNickname(e) {
    const name = (e.detail && e.detail.nickname) || '';
    if (name) this.setData({ draft: name });
  },

  async onSave() {
    const nickname = (this.data.draft || '').trim();
    if (!nickname) {
      wx.showToast({ title: '请填写昵称', icon: 'none' });
      return;
    }
    if (nickname.length > 20) {
      wx.showToast({ title: '昵称不能超过 20 字', icon: 'none' });
      return;
    }
    this.setData({ saving: true });
    try {
      const r = await request('POST', '/api/wx/profile', { nickname }, true);
      const saved = (r && r.nickname) || nickname;
      // 写回 globalData（app.js / profile.js 都依赖）
      app.globalData.nickname = saved;
      wx.showToast({ title: '已保存', icon: 'success' });
      // 短暂停留让 toast 显示
      setTimeout(() => {
        const pages = getCurrentPages();
        if (pages.length > 1) {
          wx.navigateBack({ delta: 1, fail: () => wx.switchTab({ url: '/pages/index/index' }) });
        } else {
          // 直接从此页启动的（如拦截跳转），跳到首页
          wx.switchTab({ url: '/pages/index/index' });
        }
      }, 400);
    } catch (err) {
      const msg = (err && err.message) || '保存失败';
      if (msg.includes('已被占用') || msg.includes('409')) {
        wx.showToast({ title: '昵称已被占用，请换一个', icon: 'none' });
      } else {
        wx.showToast({ title: msg, icon: 'none' });
      }
    } finally {
      this.setData({ saving: false });
    }
  },

  onBack() {
    if (this.data.allowBack) wx.navigateBack({ delta: 1 });
  }
});
