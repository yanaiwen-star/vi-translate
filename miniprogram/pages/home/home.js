// pages/home/home.js
const app = getApp();
const content = require('../../utils/content.js');

Page({
  data: {
    phone: '13077711058',
    wechat: '39446846',
    // 核心服务速览
    services: [
      { id: 'si', icon: '🎙️', name: '越南语同声传译', desc: '会议 · 论坛 · 商务实时同传' },
      { id: 'ot', icon: '🤝', name: '越南语陪同口译', desc: '考察 · 谈判 · 现场随行' },
      { id: 'tr', icon: '📄', name: '越南语笔译', desc: '合同 · 标书 · 证件文书' },
      { id: 'ai', icon: '🤖', name: 'AI 实时同传', desc: '悦迅自研 · 中越双向自动' }
    ],
    // 核心优势
    advantages: [
      { icon: '🏆', title: '14 年越南语基因', desc: '自 2011 年起只做越南语，积累深厚语料与译员资源。' },
      { icon: '⚡', title: '独家 AI 同传工具', desc: '自研中越同传引擎，会议、商务场景即开即用。' },
      { icon: '🎯', title: '专注越南语翻译', desc: '不被大而全稀释，越南语才是我们的专业主场。' }
    ]
  },

  onLoad() {
    content.fetchContent().then(c => {
      this.setData({
        phone: c.contact.phone,
        wechat: c.contact.wechat,
        services: c.homeQuick,
        advantages: c.advantages
      });
    }).catch(() => {});
  },

  // 跳转到同传工具
  goTranslate() {
    wx.switchTab({ url: '/pages/index/index' });
  },

  // 跳转到服务页
  goServices() {
    wx.switchTab({ url: '/pages/services/services' });
  },

  // 跳转到关于页
  goAbout() {
    wx.switchTab({ url: '/pages/about/about' });
  },

  // 拨打咨询电话
  onCall() {
    wx.makePhoneCall({ phoneNumber: this.data.phone });
  },

  // 复制微信号
  onCopyWechat() {
    wx.setClipboardData({
      data: this.data.wechat,
      success: () => wx.showToast({ title: '微信号已复制', icon: 'none' })
    });
  },

  // 分享
  onShareAppMessage() {
    return {
      title: '悦迅翻译 — 专注于越南语翻译服务的公司',
      path: '/pages/home/home'
    };
  }
});
