const app = getApp();
const directoryApi = require('../../utils/directory-api.js');

const STATUS_LABELS = { pending: '待处理', approved: '已同意', rejected: '已拒绝', revoked: '已撤销', expired: '已过期' };

function decorate(item) { return Object.assign({}, item, { statusLabel: STATUS_LABELS[item.status] || item.status }); }

Page({
  data: { loading: true, error: '', received: [], sent: [], activeTab: 'received', grantedContacts: null },
  onShow() { this.loadRequests(); },
  async loadRequests() {
    this.setData({ loading: true, error: '' });
    try {
      await app.login();
      const result = await directoryApi.listContactRequests();
      this.setData({ loading: false, received: (result.received || []).map(decorate), sent: (result.sent || []).map(decorate) });
    } catch (err) { this.setData({ loading: false, error: (err && err.message) || '申请加载失败' }); }
  },
  onTab(e) { this.setData({ activeTab: e.currentTarget.dataset.tab, grantedContacts: null }); },
  async onApprove(e) { await this.action(directoryApi.approveContact, e.currentTarget.dataset.id, '已同意'); },
  async onReject(e) { await this.action(directoryApi.rejectContact, e.currentTarget.dataset.id, '已拒绝'); },
  async onRevoke(e) { await this.action(directoryApi.revokeContact, e.currentTarget.dataset.id, '已撤销'); },
  async action(fn, id, title) {
    try { await fn(id); wx.showToast({ title, icon: 'success' }); this.loadRequests(); }
    catch (err) { wx.showToast({ title: (err && err.message) || '操作失败', icon: 'none' }); }
  },
  async onViewContact(e) {
    try {
      const result = await directoryApi.getGrantedContact(e.currentTarget.dataset.id);
      this.setData({ grantedContacts: result.contacts || {} });
    } catch (err) { wx.showToast({ title: (err && err.message) || '授权已失效', icon: 'none' }); }
  },
  onCloseContact() { this.setData({ grantedContacts: null }); },
  onRetry() { this.loadRequests(); }
});

module.exports = { decorate };
