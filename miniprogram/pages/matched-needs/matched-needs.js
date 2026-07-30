const app = getApp();
const directoryApi = require('../../utils/directory-api.js');
Page({
  data: { loading: true, error: '', items: [], respondingId: '' },
  onShow() { this.loadNeeds(); },
  async loadNeeds() {
    this.setData({ loading: true, error: '' });
    try { await app.login(); const result = await directoryApi.listMatchedNeeds(); this.setData({ loading: false, items: result.items || [] }); }
    catch (err) { this.setData({ loading: false, error: (err && err.message) || '需求加载失败' }); }
  },
  async onRespond(e) {
    const id = e.currentTarget.dataset.id;
    if (this.data.respondingId) return;
    this.setData({ respondingId: id });
    try { await directoryApi.respondToNeed(id); wx.showToast({ title: '已表示愿意联系', icon: 'success' }); this.loadNeeds(); }
    catch (err) { wx.showToast({ title: (err && err.message) || '响应失败', icon: 'none' }); }
    finally { this.setData({ respondingId: '' }); }
  },
  onRetry() { this.loadNeeds(); }
});
