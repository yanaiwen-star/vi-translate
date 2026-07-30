// pages/history/history.js
const sessionUtil = require('../../utils/session.js');

Page({
  data: {
    sessions: [],
    loading: false,
    selectedSession: null,
    messages: []
  },

  onShow() {
    this.loadSessions();
  },

  onPullDownRefresh() {
    this.loadSessions().then(() => {
      wx.stopPullDownRefresh();
    });
  },

  async loadSessions() {
    this.setData({ loading: true });
    const list = await sessionUtil.listSessions(100);
    this.setData({ sessions: list, loading: false });
  },

  async onSelectSession(e) {
    const { id } = e.currentTarget.dataset;
    const session = this.data.sessions.find(s => s._id === id);
    if (!session) return;
    const messages = await sessionUtil.getMessages(id);
    this.setData({
      selectedSession: session,
      messages
    });
  },

  onCloseDetail() {
    this.setData({ selectedSession: null, messages: [] });
  },

  async onDeleteSession(e) {
    const { id } = e.currentTarget.dataset;
    wx.showModal({
      title: '删除会话',
      content: '该会话的所有消息将被永久删除',
      confirmColor: '#ea4335',
      success: async (res) => {
        if (res.confirm) {
          await sessionUtil.deleteSession(id);
          if (this.data.selectedSession && this.data.selectedSession._id === id) {
            this.setData({ selectedSession: null, messages: [] });
          }
          this.loadSessions();
          wx.showToast({ title: '已删除', icon: 'success' });
        }
      }
    });
  },

  formatTime(ts) {
    const d = new Date(ts);
    const now = new Date();
    const diff = now - d;
    const oneDay = 24 * 3600 * 1000;
    if (diff < oneDay && d.getDate() === now.getDate()) {
      return `今天 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    }
    if (diff < 2 * oneDay) {
      return `昨天 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    }
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  }
});