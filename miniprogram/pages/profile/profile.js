// pages/profile/profile.js
const app = getApp();
const { request, setTokens } = require('../../utils/api.js');

Page({
  data: {
    openid: '',
    phone: '',
    nickname: '',
    userId: '',
    editing: false,
    draftNickname: '',
    quotaMinutes: 0
  },

  onShow() {
    this.refreshQuota();
    this.setData({
      openid: app.globalData.openid || '',
      phone: app.globalData.phone || '',
      nickname: app.globalData.nickname || '',
      // 后端 user_id 格式 wxmp_{openid}@mp.local（见 app/auth/wechat_identity.py:_placeholder_email）
      userId: app.globalData.openid ? `wxmp_${app.globalData.openid}@mp.local` : ''
    });
  },

  // 复制用户ID：便于在「我的」页给运营/客服报自己的 user_id 以便后台对齐
  onCopyUserId() {
    const id = this.data.userId;
    if (!id) {
      wx.showToast({ title: '请先登录', icon: 'none' });
      return;
    }
    wx.setClipboardData({
      data: id,
      success: () => wx.showToast({ title: '用户ID已复制', icon: 'success' }),
      fail: () => wx.showToast({ title: '复制失败', icon: 'none' })
    });
  },

  // 加入越南语互助群：复制微信号 39446846（与 onFeedback 一致，便于加群引流）
  onCopyWechatGroup() {
    wx.setClipboardData({
      data: '39446846',
      success: () => wx.showToast({
        title: '微信号已复制，备注「越南语」进群',
        icon: 'none',
        duration: 2500
      }),
      fail: () => wx.showToast({ title: '复制失败', icon: 'none' })
    });
  },

  // 进入昵称编辑：用 input[type=nickname] 既能手填自定义名，
  // 也能点键盘上的「使用微信昵称」一键回填微信名称。
  onEditName() {
    this.setData({ editing: true, draftNickname: this.data.nickname || '' });
  },
  onCancelEdit() {
    this.setData({ editing: false, draftNickname: '' });
  },
  onNicknameInput(e) {
    this.setData({ draftNickname: e.detail.value });
  },
  // 用户点选「使用微信昵称」时，微信回填真实昵称
  onWechatNickname(e) {
    const name = (e.detail && e.detail.nickname) || '';
    if (name) this.setData({ draftNickname: name });
  },
  async onSaveName() {
    const nickname = (this.data.draftNickname || '').trim();
    wx.showLoading({ title: '保存中' });
    try {
      const r = await request('POST', '/api/wx/profile', { nickname }, true);
      wx.hideLoading();
      if (r && 'nickname' in r) {
        app.globalData.nickname = r.nickname || '';
        this.setData({ nickname: r.nickname || '', editing: false, draftNickname: '' });
        wx.showToast({ title: '已保存', icon: 'success' });
        // 昵称奖励（+10 分钟）已落库，刷新剩余时长展示
        this.refreshQuota();
      } else {
        wx.hideLoading();
        wx.showToast({ title: '保存失败', icon: 'none' });
      }
    } catch (err) {
      wx.hideLoading();
      wx.showToast({ title: (err && err.message) || '保存失败', icon: 'none' });
    }
  },

  // 拉取唯一「剩余同传时长」：后端 /billing/quota 返回的 available_minutes
  // 已汇总所有池（注册30 + 昵称10 + 手机20 + 已购时长包），不区分免费/付费。
  refreshQuota() {
    request('GET', '/billing/quota', {}, true).then((res) => {
      if (res && typeof res.available_minutes === 'number') {
        this.setData({ quotaMinutes: Math.max(0, res.available_minutes) });
      }
    }).catch(() => {});
  },

  onOpenPricing() {
    wx.navigateTo({ url: '/pages/pricing/pricing' });
  },

  onOpenQwenSettings() {
    wx.navigateTo({ url: '/pages/qwen-settings/qwen-settings' });
  },

  onFeedback() {
    wx.showModal({
      title: '意见反馈',
      content: '欢迎致电 13077711058，或添加微信 39446846 与我们联系',
      confirmText: '拨打电话',
      success: (res) => {
        if (res.confirm) {
          wx.makePhoneCall({ phoneNumber: '13077711058' });
        }
      }
    });
  },

  onAbout() {
    // 关于 不是 tabBar 页面，必须用 navigateTo（switchTab 只能跳 tabBar，
    // 跳非 tabBar 会静默失败 + 看起来"没反应"）
    wx.navigateTo({ url: '/pages/about/about' });
  },

  noop() {},

  // 微信手机号绑定：getPhoneNumber 拿到 code，POST /api/wx/phone 解密落库
  // 若该手机号已绑定网页账号，后端会合并账户并换发新 token，需同步更新本地。
  onBindPhone(e) {
    const code = e.detail && e.detail.code;
    if (!code) {
      wx.showToast({ title: '未能获取手机号，请重试', icon: 'none' });
      return;
    }
    wx.showLoading({ title: '绑定中' });
    request('POST', '/api/wx/phone', { code }, true).then((r) => {
      wx.hideLoading();
      if (r && r.phone) {
        app.globalData.phone = r.phone;
        this.setData({ phone: r.phone });
        // 触发了账户合并：后端换发新 token，更新本地存储与全局态
        if (r.access_token) {
          setTokens(r.access_token, r.refresh_token);
          app.globalData.accessToken = r.access_token;
          app.globalData.openid = r.openid || app.globalData.openid;
        }
        wx.showToast({ title: '绑定成功', icon: 'success' });
        // 手机号奖励（+20 分钟）已落库，刷新剩余时长展示
        this.refreshQuota();
      } else {
        wx.showToast({ title: '绑定失败', icon: 'none' });
      }
    }).catch((err) => {
      wx.hideLoading();
      wx.showToast({ title: (err && err.message) || '绑定失败', icon: 'none' });
    });
  }
});
