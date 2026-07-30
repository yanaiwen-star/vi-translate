const app = getApp();
const directoryApi = require('../../utils/directory-api.js');
const STATUS_LABELS = { open: '等待响应', closed: '已完成', withdrawn: '已撤回', expired: '已过期' };
function decorate(item) { return Object.assign({}, item, { statusLabel: STATUS_LABELS[item.status] || item.status }); }
Page({
  data: { loading: true, error: '', items: [] },
  onShow() { this.loadNeeds(); },
  async loadNeeds() {
    this.setData({ loading: true, error: '' });
    try { await app.login(); const result = await directoryApi.listMyNeeds(); this.setData({ loading: false, items: (result.items || []).map(decorate) }); }
    catch (err) { this.setData({ loading: false, error: (err && err.message) || '需求加载失败' }); }
  },
  onWithdraw(e) {
    const id = e.currentTarget.dataset.id;
    wx.showModal({ title: '撤回需求', content: '撤回后需求和译员响应会立即删除。', success: async (res) => {
      if (!res.confirm) return;
      try { await directoryApi.withdrawNeed(id); wx.showToast({ title: '已撤回', icon: 'success' }); this.loadNeeds(); }
      catch (err) { wx.showToast({ title: (err && err.message) || '撤回失败', icon: 'none' }); }
    } });
  },
  onPublish() { wx.navigateTo({ url: '/pages/business-publish/business-publish' }); },
  onRetry() { this.loadNeeds(); }
});
module.exports = { decorate };
