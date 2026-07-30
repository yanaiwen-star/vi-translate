const app = getApp();
const { request } = require('../../utils/api.js');

Page({
  data: {
    mode: 'platform',
    configured: false,
    keyMasked: '',
    apiKey: '',
    regions: [
      { code: 'mainland', label: '中国内地（有新人免费额度）' },
      { code: 'intl', label: '国际 / 新加坡（无新人免费额度）' }
    ],
    regionIndex: 0,
    saving: false
  },

  async onLoad() {
    const mode = wx.getStorageSync('qwen_provider_mode') === 'byok' ? 'byok' : 'platform';
    this.setData({ mode });
    await this.loadCredential();
  },

  async loadCredential() {
    try {
      await app.login();
      const result = await request('GET', '/api/qwen-credential', {}, true);
      const regionIndex = result.region === 'intl' ? 1 : 0;
      this.setData({
        configured: !!result.configured,
        keyMasked: result.key_masked || '',
        regionIndex
      });
      if (!result.configured && this.data.mode === 'byok') this.usePlatform();
    } catch (err) {
      wx.showToast({ title: err.message || '读取配置失败', icon: 'none' });
    }
  },

  usePlatform() {
    wx.setStorageSync('qwen_provider_mode', 'platform');
    this.setData({ mode: 'platform' });
  },

  useByok() {
    if (!this.data.configured) {
      wx.showToast({ title: '请先保存百炼 API Key', icon: 'none' });
      return;
    }
    wx.setStorageSync('qwen_provider_mode', 'byok');
    this.setData({ mode: 'byok' });
  },

  onKeyInput(e) {
    this.setData({ apiKey: e.detail.value || '' });
  },

  onRegionChange(e) {
    this.setData({ regionIndex: Number(e.detail.value) || 0 });
  },

  copyApplyUrl() {
    wx.setClipboardData({
      data: 'https://bailian.console.aliyun.com/?tab=model#/api-key',
      success: () => wx.showToast({ title: '申请地址已复制', icon: 'success' })
    });
  },

  async saveKey() {
    const apiKey = (this.data.apiKey || '').trim();
    if (!apiKey.startsWith('sk-')) {
      wx.showToast({ title: '请输入正确的 sk- API Key', icon: 'none' });
      return;
    }
    this.setData({ saving: true });
    try {
      await app.login();
      const region = this.data.regions[this.data.regionIndex].code;
      const result = await request('PUT', '/api/qwen-credential', { api_key: apiKey, region }, true);
      wx.setStorageSync('qwen_provider_mode', 'byok');
      this.setData({
        configured: true,
        keyMasked: result.key_masked || '',
        apiKey: '',
        mode: 'byok'
      });
      wx.showToast({ title: '已安全保存', icon: 'success' });
    } catch (err) {
      wx.showToast({ title: err.message || '保存失败', icon: 'none' });
    } finally {
      this.setData({ saving: false });
    }
  },

  deleteKey() {
    wx.showModal({
      title: '删除 API Key',
      content: '删除后将自动切换回平台托管服务。',
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await request('DELETE', '/api/qwen-credential', {}, true);
          wx.setStorageSync('qwen_provider_mode', 'platform');
          this.setData({ configured: false, keyMasked: '', apiKey: '', mode: 'platform' });
          wx.showToast({ title: '已删除', icon: 'success' });
        } catch (err) {
          wx.showToast({ title: err.message || '删除失败', icon: 'none' });
        }
      }
    });
  }
});
