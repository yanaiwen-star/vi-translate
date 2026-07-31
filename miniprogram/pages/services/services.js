const app = getApp();
const directoryApi = require('../../utils/directory-api.js');
const { mergeAndSortProfiles } = require('../../utils/directory.js');

const LANGUAGE_LABELS = {
  vi: '越南语', zh: '中文', en: '英语', th: '泰语', lo: '老挝语',
  km: '柬埔寨语', ja: '日语', ko: '韩语', fr: '法语'
};
const SERVICE_LABELS = {
  interpretation: '口译', translation: '笔译', simultaneous: '同传', escort: '陪同',
  business: '商务', legal: '法律', technical: '技术', tourism: '旅游'
};

function decorate(item) {
  return Object.assign({}, item, {
    languageLabels: (item.language_codes || []).map((code) => LANGUAGE_LABELS[code] || code),
    serviceLabels: (item.service_codes || []).map((code) => SERVICE_LABELS[code] || code),
    subjectLabel: item.subject_type === 'company' ? '翻译公司' : '个人译员',
    modeLabel: item.service_mode === 'online' ? '线上' : (item.service_mode === 'offline' ? '线下' : '线上/线下'),
    verificationLabel: item.verification_status === 'verified' ? '已认证' : '未认证，请自行核实',
    exampleLabel: item.is_example ? '示例资料·招募中' : ''
  });
}

Page({
  data: {
    loading: true,
    loadingMore: false,
    error: '',
    profiles: [],
    total: 0,
    page: 1,
    hasMore: false,
    keyword: '',
    language: 'vi',
    country: '',
    city: '',
    service: '',
    mode: '',
    subjectType: '',
    showFilters: false,
    languages: [
      { code: 'vi', label: '越南语' },
      { code: '', label: '全部' },
      { code: 'zh', label: '中文' },
      { code: 'en', label: '英语' },
      { code: 'th', label: '泰语' }
    ],
    countries: [
      { code: '', label: '不限国家' }, { code: 'CN', label: '中国' },
      { code: 'VN', label: '越南' }, { code: 'TH', label: '泰国' }
    ],
    services: [
      { code: '', label: '不限服务' }, { code: 'interpretation', label: '口译' },
      { code: 'translation', label: '笔译' }, { code: 'simultaneous', label: '同传' },
      { code: 'escort', label: '陪同' }, { code: 'business', label: '商务' },
      { code: 'legal', label: '法律' }, { code: 'technical', label: '技术' }
    ]
  },

  onLoad() {
    if (wx.showShareMenu) wx.showShareMenu({ menus: ['shareAppMessage', 'shareTimeline'] });
    this.loadProfiles(true);
  },
  onShow() { if (!this.data.loading && this.data.profiles.length) this.loadProfiles(true); },
  onPullDownRefresh() { this.loadProfiles(true).finally(() => wx.stopPullDownRefresh()); },
  onReachBottom() { if (this.data.hasMore && !this.data.loadingMore) this.loadProfiles(false); },

  filters(page) {
    return {
      language: this.data.language,
      country: this.data.country,
      city: (this.data.city || '').trim(),
      service: this.data.service,
      mode: this.data.mode,
      subject_type: this.data.subjectType,
      keyword: (this.data.keyword || '').trim(),
      page,
      page_size: 20
    };
  },

  async loadProfiles(reset) {
    const page = reset ? 1 : this.data.page + 1;
    this.setData(reset ? { loading: true, error: '' } : { loadingMore: true, error: '' });
    try {
      const result = await directoryApi.listProfiles(this.filters(page));
      const next = (result.items || []).map(decorate);
      const rows = reset ? next : this.data.profiles.concat(next);
      const ordered = mergeAndSortProfiles(rows);
      this.setData({
        profiles: ordered,
        total: Number(result.total) || ordered.length,
        page,
        hasMore: ordered.length < (Number(result.total) || ordered.length),
        loading: false,
        loadingMore: false
      });
    } catch (err) {
      this.setData({
        loading: false,
        loadingMore: false,
        error: (err && err.message) || '目录加载失败，请重试'
      });
    }
  },

  onKeywordInput(e) { this.setData({ keyword: e.detail.value }); },
  onSearch() { this.loadProfiles(true); },
  onChooseLanguage(e) { this.setData({ language: e.currentTarget.dataset.code }); this.loadProfiles(true); },
  onToggleFilters() { this.setData({ showFilters: !this.data.showFilters }); },
  onCountryChange(e) { this.setData({ country: this.data.countries[Number(e.detail.value)].code }); },
  onServiceChange(e) { this.setData({ service: this.data.services[Number(e.detail.value)].code }); },
  onCityInput(e) { this.setData({ city: e.detail.value }); },
  onModeChange(e) { this.setData({ mode: e.currentTarget.dataset.code }); },
  onSubjectChange(e) { this.setData({ subjectType: e.currentTarget.dataset.code }); },
  onApplyFilters() { this.setData({ showFilters: false }); this.loadProfiles(true); },
  onResetFilters() {
    this.setData({ country: '', city: '', service: '', mode: '', subjectType: '' });
    this.loadProfiles(true);
  },
  onRetry() { this.loadProfiles(true); },
  onOpenProfile(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: '/pages/translator-detail/translator-detail?id=' + encodeURIComponent(id) });
  },
  async onJoin() {
    await app.login();
    wx.navigateTo({ url: '/pages/translator-edit/translator-edit' });
  },
  onShareAppMessage() {
    return { title: '悦迅翻译｜免费找译员和翻译公司', path: '/pages/services/services' };
  },
  onShareTimeline() {
    return { title: '悦迅翻译｜免费找译员和翻译公司' };
  }
});

module.exports = { decorate };
