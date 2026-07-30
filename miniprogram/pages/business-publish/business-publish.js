const app = getApp();
const directoryApi = require('../../utils/directory-api.js');

Page({
  data: {
    submitting: false,
    sourceOptions: [{ code: 'zh', label: '中文' }, { code: 'vi', label: '越南语' }, { code: 'en', label: '英语' }],
    targetOptions: [{ code: 'vi', label: '越南语' }, { code: 'zh', label: '中文' }, { code: 'en', label: '英语' }],
    serviceOptions: [
      { code: 'interpretation', label: '口译' }, { code: 'translation', label: '笔译' },
      { code: 'simultaneous', label: '同传' }, { code: 'escort', label: '陪同' },
      { code: 'business', label: '商务' }, { code: 'technical', label: '技术' }
    ],
    sourceIndex: 0,
    targetIndex: 0,
    serviceIndex: 0,
    mode: 'online',
    city: '',
    serviceAt: '',
    note: '',
    responseLimit: 3
  },
  onSourceChange(e) { this.setData({ sourceIndex: Number(e.detail.value) }); },
  onTargetChange(e) { this.setData({ targetIndex: Number(e.detail.value) }); },
  onServiceChange(e) { this.setData({ serviceIndex: Number(e.detail.value) }); },
  onModeChange(e) { this.setData({ mode: e.currentTarget.dataset.code }); },
  onCityInput(e) { this.setData({ city: e.detail.value }); },
  onDateChange(e) { this.setData({ serviceAt: e.detail.value }); },
  onNoteInput(e) { this.setData({ note: e.detail.value }); },
  onLimitChange(e) { this.setData({ responseLimit: Number(e.detail.value) + 1 }); },

  async onSubmit() {
    if (this.data.submitting) return;
    const note = (this.data.note || '').trim();
    if (!note) {
      wx.showToast({ title: '请简要说明业务需求', icon: 'none' });
      return;
    }
    this.setData({ submitting: true });
    try {
      await app.login();
      const source = this.data.sourceOptions[this.data.sourceIndex];
      const target = this.data.targetOptions[this.data.targetIndex];
      const service = this.data.serviceOptions[this.data.serviceIndex];
      await directoryApi.createNeed({
        source_lang: source.code,
        target_lang: target.code,
        service_type: service.code,
        service_mode: this.data.mode,
        country_code: '',
        city: (this.data.city || '').trim(),
        service_at: this.data.serviceAt ? this.data.serviceAt + 'T00:00:00' : null,
        note,
        response_limit: this.data.responseLimit
      });
      wx.showToast({ title: '业务已发布', icon: 'success' });
      setTimeout(() => wx.navigateBack(), 700);
    } catch (err) {
      wx.showToast({ title: (err && err.message) || '发布失败', icon: 'none' });
    } finally {
      this.setData({ submitting: false });
    }
  }
});
