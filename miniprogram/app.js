// app.js
const { request, setTokens } = require('./utils/api.js');

App({
  globalData: {
    userInfo: null,
    openid: null,
    unionid: null,
    phone: null,
    nickname: null,
    accessToken: null,
    // 当前会话
    currentSessionId: null,
    // 每日免费配额：20 分钟 = 1200 秒（超出需购买语音包）
    dailyQuota: {
      used: 0,
      limit: 1200,
      date: ''
    }
  },

  onLaunch() {
    // 同传已改用网页版 Qwen 系统（底层 DashScope realtime），不再依赖云函数

    // 微信登录 → 换取服务器 JWT（用户/历史存到 ECS 后端）
    this.login();

    // 加载配额信息
    this.loadQuota();
  },

  // 微信登录：wx.login 拿到 code，POST /api/wx/login 换 openid + JWT
  async login() {
    try {
      const { code } = await wx.login();
      if (!code) return;
      const res = await request('POST', '/api/wx/login', { code }, false);
      if (res && res.access_token) {
        setTokens(res.access_token, res.refresh_token);
        this.globalData.accessToken = res.access_token;
        this.globalData.openid = res.openid || '';
        this.globalData.unionid = res.unionid || '';
        // 拉取资料（openid/unionid/phone），用于跨端身份展示与手机号绑定
        try {
          const me = await request('GET', '/api/wx/me', {}, true);
          if (me) {
            this.globalData.openid = me.openid || this.globalData.openid;
            this.globalData.unionid = me.unionid || this.globalData.unionid;
            this.globalData.phone = me.phone || '';
            this.globalData.nickname = me.nickname || '';
          }
        } catch (e) { /* 资料拉取失败不影响登录 */ }
      }
    } catch (err) {
      console.error('服务器登录失败，历史记录将仅本地保存', err);
    }
  },

  async loadQuota() {
    const today = new Date().toISOString().slice(0, 10);
    if (this.globalData.dailyQuota.date === today) return;
    this.globalData.dailyQuota = {
      used: 0,
      limit: 1200,
      date: today
    };
  },

  // 更新配额使用（本地估算；仅在 onStop 录音结束时调用一次）
  updateQuota(seconds) {
    this.globalData.dailyQuota.used += seconds;
  },

  // 检查配额：异步从 server 拉真实剩余（不依赖 in-memory 计数，避免反复录音累积漂移）。
  // 失败时兜底用 in-memory 状态。返回 boolean：true=还有剩余。
  async checkQuota() {
    try {
      const r = await request('GET', '/billing/quota', {}, true);
      if (r && typeof r.available_minutes === 'number') {
        const today = new Date().toISOString().slice(0, 10);
        this.globalData.dailyQuota.date = today;
        // 信任 server 返回的 available_minutes（剩余分钟）。limit 字段仅用于「我的」页展示。
        this.globalData.dailyQuota.limit = 20 * 60; // 20 分钟 = 1200 秒（与 HEAD 文案对齐，server 端用满 20 分钟也会归零）
        this.globalData.dailyQuota.used = Math.max(0, this.globalData.dailyQuota.limit - r.available_minutes * 60);
        return r.available_minutes > 0;
      }
    } catch (e) {
      // server 不可达：兜底用 in-memory
    }
    return this.globalData.dailyQuota.used < this.globalData.dailyQuota.limit;
  },

  // 半拦：检测昵称是否设置；如未设置，跳强制设置页（用于"首次发起需要用户身份的操作"前）。
  // options.from = 发起拦截的位置（如 'live' 同传），会传给 set-nickname 页用于显示原因。
  // 同步返回 boolean：true = 已设昵称或不需要拦，false = 已跳走（调用方应中止操作）。
  ensureNickname(opts) {
    opts = opts || {};
    if ((this.globalData.nickname || '').trim()) return true;
    const url = '/pages/set-nickname/set-nickname' +
      '?from=' + encodeURIComponent(opts.from || 'app') +
      (opts.reason ? '&reason=' + encodeURIComponent(opts.reason) : '');
    wx.navigateTo({ url });
    return false;
  }
});
