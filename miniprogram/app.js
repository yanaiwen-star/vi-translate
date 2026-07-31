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
    // 剩余同传时长（分钟）——全局唯一的额度数字。
    // 唯一真相是服务端 /billing/quota 的 available_minutes，已汇总
    //「注册一次性赠送 + 绑定奖励 + 已购时长包」，客户端不再维护第二套免费池。
    // null = 尚未从服务端拉到（此时不拦截，避免网络抖动误杀正常用户）。
    quotaMinutes: null,
    // 注册一次性赠送分钟数：仅用于定价页的政策文案展示，与「剩余时长」无关。
    freeGrantMinutes: 30
  },

  onLaunch() {
    // 全局解锁 iOS 音频会话：微信 iOS 上 InnerAudioContext 默认受系统静音键 /
    // 环境音频会话(category)影响，不调用此 API 会导致同传/面对面/消息的语音完全不响。
    // 必须在任何播放前设置一次（全局生效，覆盖所有页面的音频上下文）。
    if (wx.setInnerAudioOption) {
      wx.setInnerAudioOption({ obeyMuteSwitch: false, mixWithOther: true });
    }

    // 同传已改用网页版 Qwen 系统（底层 DashScope realtime），不再依赖云函数

    // 微信登录 → 换取服务器 JWT（用户/历史存到 ECS 后端）
    // 配额必须登录后才能拉（接口需要 JWT），因此串在 login 之后。
    this.login().then(() => this.loadQuota());
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

  // 启动时拉一次真实剩余时长（服务器是唯一真相；失败则保持 null，
  // 真正的拦截仍以每次开播前的 checkQuota() 为准）。
  async loadQuota() {
    try {
      const r = await request('GET', '/billing/quota', {}, true);
      if (r && typeof r.available_minutes === 'number') {
        this.globalData.quotaMinutes = Math.max(0, r.available_minutes);
      }
    } catch (e) {
      // 未登录或网络不可达：保持 null，不阻塞启动
    }
  },

  // 本地估算扣减（仅在 onStop 录音结束时调用一次）；下次 checkQuota 会用服务端值校正。
  updateQuota(seconds) {
    if (typeof this.globalData.quotaMinutes !== 'number') return;
    const usedMin = Math.max(0, Math.round((seconds || 0) / 60));
    this.globalData.quotaMinutes = Math.max(0, this.globalData.quotaMinutes - usedMin);
  },

  // 检查剩余时长：异步从 server 拉真实剩余（不依赖本地计数，避免反复录音累积漂移）。
  // 返回 boolean：true=还有剩余。服务端不可达时不拦截，避免网络抖动误杀正常用户。
  async checkQuota() {
    try {
      const r = await request('GET', '/billing/quota', {}, true);
      if (r && typeof r.available_minutes === 'number') {
        this.globalData.quotaMinutes = Math.max(0, r.available_minutes);
        return r.available_minutes > 0;
      }
    } catch (e) {
      // server 不可达：落到下面的兜底判断
    }
    return this.globalData.quotaMinutes === null || this.globalData.quotaMinutes > 0;
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
