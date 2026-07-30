const app = getApp();
const directoryApi = require('../../utils/directory-api.js');

Page({
  data: {
    reasons: [
      { code: 'fake_identity', label: '身份或资料疑似不真实' },
      { code: 'illegal_content', label: '违法或违规内容' },
      { code: 'harassment', label: '骚扰或不当联系' },
      { code: 'unreachable', label: '长期无法联系' },
      { code: 'other', label: '其他问题' }
    ],
    reason: 'fake_identity', note: '', submitting: false
  },
  onLoad(options) { this.profileId = decodeURIComponent(options.id || ''); },
  onReason(e) { this.setData({ reason: e.currentTarget.dataset.code }); },
  onNoteInput(e) { this.setData({ note: e.detail.value }); },
  async onSubmit() {
    if (this.data.submitting) return;
    this.setData({ submitting: true });
    try {
      await app.login();
      await directoryApi.reportProfile(this.profileId, { reason: this.data.reason, note: (this.data.note || '').trim() });
      wx.showToast({ title: '举报已提交', icon: 'success' });
      setTimeout(() => wx.navigateBack(), 600);
    } catch (err) {
      wx.showToast({ title: (err && err.message) || '提交失败', icon: 'none' });
    } finally { this.setData({ submitting: false }); }
  }
});
