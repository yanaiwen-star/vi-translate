// pages/about/about.js
const content = require('../../utils/content.js');

Page({
  data: {
    phone: '13077711058',
    wechat: '39446846',
    email: '39446846@qq.com',
    address: '广西民族大学北门相思湖畔A区商铺206',
    latitude: 22.836,
    longitude: 108.256,
    credentials: [
      '中央民族语文翻译局',
      '中央人民广播电台越语部',
      '中国国际广播电台越语部',
      '中央民族大学越南语专业',
      '北京大学东方语言学系'
    ]
  },

  onLoad() {
    content.fetchContent().then(c => {
      this.setData({
        phone: c.contact.phone,
        wechat: c.contact.wechat,
        email: c.contact.email,
        address: c.contact.address,
        latitude: c.contact.latitude,
        longitude: c.contact.longitude,
        credentials: c.about.credentials
      });
    }).catch(() => {});
  },

  onCall() {
    wx.makePhoneCall({ phoneNumber: this.data.phone });
  },

  onCopyWechat() {
    wx.setClipboardData({
      data: this.data.wechat,
      success: () => wx.showToast({ title: '微信号已复制', icon: 'none' })
    });
  },

  onCopyEmail() {
    wx.setClipboardData({
      data: this.data.email,
      success: () => wx.showToast({ title: '邮箱已复制', icon: 'none' })
    });
  },

  onOpenLocation() {
    wx.openLocation({
      latitude: this.data.latitude,
      longitude: this.data.longitude,
      name: '南宁市悦迅翻译有限公司',
      address: this.data.address,
      scale: 16
    });
  },

  onShareAppMessage() {
    return {
      title: '悦迅翻译 — 专注于越南语翻译服务的公司',
      path: '/pages/about/about'
    };
  }
});
