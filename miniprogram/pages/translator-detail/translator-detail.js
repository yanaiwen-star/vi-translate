const app = getApp();
const directoryApi = require('../../utils/directory-api.js');

const LANGUAGE_LABELS = { vi: '越南语', zh: '中文', en: '英语', th: '泰语', lo: '老挝语', km: '柬埔寨语', ja: '日语', ko: '韩语', fr: '法语' };
const SERVICE_LABELS = { interpretation: '口译', translation: '笔译', simultaneous: '同传', escort: '陪同', business: '商务', legal: '法律', technical: '技术', tourism: '旅游' };

Page({
  data: { loading: true, error: '', profile: null, requesting: false, showRequest: false, purpose: '' },
  onLoad(options) { this.profileId = decodeURIComponent(options.id || ''); this.loadProfile(); },
  async loadProfile() {
    this.setData({ loading: true, error: '' });
    try {
      const item = await directoryApi.getProfile(this.profileId);
      const profile = Object.assign({}, item, {
        languageLabels: (item.language_codes || []).map((code) => LANGUAGE_LABELS[code] || code),
        serviceLabels: (item.service_codes || []).map((code) => SERVICE_LABELS[code] || code),
        verificationLabel: item.verification_status === 'verified' ? '已认证' : '未认证，请自行核实'
      });
      this.setData({ loading: false, profile });
    } catch (err) { this.setData({ loading: false, error: (err && err.message) || '资料加载失败' }); }
  },
  onShowRequest() {
    const profile = this.data.profile;
    if (!profile || profile.is_example || !profile.contact_request_allowed) return;
    this.setData({ showRequest: true });
  },
  onCancelRequest() { this.setData({ showRequest: false, purpose: '' }); },
  onPurposeInput(e) { this.setData({ purpose: e.detail.value }); },
  async onRequestContact() {
    if (this.data.requesting) return;
    const purpose = (this.data.purpose || '').trim();
    if (!purpose) { wx.showToast({ title: '请填写联系用途', icon: 'none' }); return; }
    this.setData({ requesting: true });
    try {
      await app.login();
      await directoryApi.requestContact(this.profileId, purpose);
      this.setData({ requesting: false, showRequest: false, purpose: '' });
      wx.showToast({ title: '申请已提交', icon: 'success' });
    } catch (err) {
      this.setData({ requesting: false });
      wx.showToast({ title: (err && err.message) || '申请失败', icon: 'none' });
    }
  },
  onRetry() { this.loadProfile(); },
  onJoin() { wx.navigateTo({ url: '/pages/translator-edit/translator-edit' }); },
  onReport() { wx.navigateTo({ url: '/pages/report-profile/report-profile?id=' + encodeURIComponent(this.profileId) }); }
});
