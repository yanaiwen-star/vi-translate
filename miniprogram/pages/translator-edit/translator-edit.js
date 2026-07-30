const app = getApp();
const directoryApi = require('../../utils/directory-api.js');

const LANGUAGE_OPTIONS = [
  { code: 'vi', label: '越南语' }, { code: 'zh', label: '中文' }, { code: 'en', label: '英语' },
  { code: 'th', label: '泰语' }, { code: 'lo', label: '老挝语' }, { code: 'km', label: '柬埔寨语' },
  { code: 'ja', label: '日语' }, { code: 'ko', label: '韩语' }, { code: 'fr', label: '法语' }
];
const SERVICE_OPTIONS = [
  { code: 'interpretation', label: '口译' }, { code: 'translation', label: '笔译' },
  { code: 'simultaneous', label: '同声传译' }, { code: 'escort', label: '陪同翻译' },
  { code: 'business', label: '商务翻译' }, { code: 'legal', label: '法律翻译' },
  { code: 'technical', label: '技术翻译' }, { code: 'tourism', label: '旅游翻译' }
];

function selectedOptions(options, selected) {
  return options.map((item) => Object.assign({}, item, { selected: (selected || []).indexOf(item.code) >= 0 }));
}

Page({
  data: {
    loading: true, saving: false, existing: false, saveError: '', status: 'active',
    subjectType: 'individual', displayName: '', bio: '', countryCode: 'CN', city: '', serviceMode: 'both',
    languages: selectedOptions(LANGUAGE_OPTIONS, ['vi', 'zh']),
    services: selectedOptions(SERVICE_OPTIONS, ['interpretation']),
    wechat: '', phone: '', email: '', agreed: false
  },
  async onLoad() {
    try {
      await app.login();
      const item = await directoryApi.getMyProfile();
      if (!item || item.exists === false) {
        this.setData({ loading: false, existing: false, saveError: '' });
        return;
      }
      const contacts = item.contacts || {};
      this.setData({
        loading: false, existing: true, status: item.status || 'active', subjectType: item.subject_type,
        displayName: item.display_name, bio: item.bio || '', countryCode: item.country_code,
        city: item.city || '', serviceMode: item.service_mode,
        languages: selectedOptions(LANGUAGE_OPTIONS, item.language_codes),
        services: selectedOptions(SERVICE_OPTIONS, item.service_codes),
        wechat: contacts.wechat || '', phone: contacts.phone || '', email: contacts.email || '', agreed: true
      });
    } catch (err) {
      const missing = err && /尚未创建|404|不存在/.test(err.message || '');
      this.setData({ loading: false, existing: false, saveError: missing ? '' : ((err && err.message) || '资料加载失败') });
    }
  },
  onTextInput(e) { const data = {}; data[e.currentTarget.dataset.field] = e.detail.value; this.setData(data); },
  onSubjectChange(e) { this.setData({ subjectType: e.currentTarget.dataset.code }); },
  onModeChange(e) { this.setData({ serviceMode: e.currentTarget.dataset.code }); },
  onToggleLanguage(e) {
    const code = e.currentTarget.dataset.code;
    this.setData({ languages: this.data.languages.map((item) => item.code === code ? Object.assign({}, item, { selected: !item.selected }) : item) });
  },
  onToggleService(e) {
    const code = e.currentTarget.dataset.code;
    this.setData({ services: this.data.services.map((item) => item.code === code ? Object.assign({}, item, { selected: !item.selected }) : item) });
  },
  onAgreementChange(e) { this.setData({ agreed: (e.detail.value || []).indexOf('agree') >= 0 }); },
  payload() {
    return {
      subject_type: this.data.subjectType,
      display_name: (this.data.displayName || '').trim(),
      bio: (this.data.bio || '').trim(),
      country_code: (this.data.countryCode || '').trim().toUpperCase(),
      city: (this.data.city || '').trim(),
      service_mode: this.data.serviceMode,
      languages: this.data.languages.filter((item) => item.selected).map((item) => item.code),
      services: this.data.services.filter((item) => item.selected).map((item) => item.code),
      contacts: { wechat: (this.data.wechat || '').trim(), phone: (this.data.phone || '').trim(), email: (this.data.email || '').trim() }
    };
  },
  async onSave() {
    if (this.data.saving) return;
    const payload = this.payload();
    if (!payload.display_name || !payload.languages.length || !payload.services.length) { wx.showToast({ title: '请完善名称、语种和服务', icon: 'none' }); return; }
    if (!this.data.agreed) { wx.showToast({ title: '请确认资料发布声明', icon: 'none' }); return; }
    this.setData({ saving: true, saveError: '' });
    try {
      const result = this.data.existing ? await directoryApi.updateProfile(payload) : await directoryApi.createProfile(payload);
      this.setData({ saving: false, existing: true, status: result.status || 'active' });
      wx.showToast({ title: '资料已保存', icon: 'success' });
    } catch (err) {
      this.setData({ saving: false, saveError: (err && err.message) || '保存失败，请重试' });
    }
  },
  async onToggleStatus() {
    try {
      const result = this.data.status === 'active' ? await directoryApi.pauseProfile() : await directoryApi.resumeProfile();
      this.setData({ status: result.status });
    } catch (err) { wx.showToast({ title: (err && err.message) || '操作失败', icon: 'none' }); }
  },
  onDelete() {
    wx.showModal({ title: '删除译员资料', content: '删除后联系方式和未完成申请会一并清除。确定继续吗？', confirmColor: '#d93025', success: async (res) => {
      if (!res.confirm) return;
      try { await directoryApi.deleteProfile(); wx.showToast({ title: '已删除', icon: 'success' }); setTimeout(() => wx.navigateBack(), 500); }
      catch (err) { wx.showToast({ title: (err && err.message) || '删除失败', icon: 'none' }); }
    } });
  },
  onVerification() { wx.showToast({ title: '实名认证暂未开放，可正常免费入驻', icon: 'none', duration: 2600 }); }
});

module.exports = { selectedOptions };
