const app = getApp();
const directoryApi = require('../../utils/directory-api.js');

const SERVICE_LABELS = {
  interpretation: '口译', translation: '笔译', simultaneous: '同传',
  escort: '陪同', business: '商务', technical: '技术'
};
const LANGUAGE_LABELS = { zh: '中文', vi: '越南语', en: '英语', th: '泰语' };

const EXAMPLE_BUSINESSES = [
  { id: 'biz-01', title: '中越商务会议口译', pair: '中文 → 越南语', service: 'interpretation', mode: '线下', location: '广西·南宁', schedule: '工作日可协调', industry: '商务洽谈', summary: '制造企业与越南合作方会议，需要熟悉商务沟通的中越口译。' },
  { id: 'biz-02', title: '越南工厂考察陪同', pair: '中文 ↔ 越南语', service: 'escort', mode: '线下', location: '越南·河内', schedule: '2—3 天', industry: '制造业', summary: '工厂参观、设备沟通和行程陪同，优先了解机械或电子行业。' },
  { id: 'biz-03', title: '产品说明书中译越', pair: '中文 → 越南语', service: 'translation', mode: '线上', location: '不限地区', schedule: '按项目交付', industry: '机电产品', summary: '产品参数、安装说明与安全提示笔译，需要统一专业术语。' },
  { id: 'biz-04', title: '展会接待双向口译', pair: '中文 ↔ 越南语', service: 'business', mode: '线下', location: '广东·广州', schedule: '展期 3 天', industry: '会展贸易', summary: '展位客户接待、产品介绍和意向沟通，需要表达自然、反应迅速。' },
  { id: 'biz-05', title: '采购合同越译中', pair: '越南语 → 中文', service: 'translation', mode: '线上', location: '不限地区', schedule: '时间可商议', industry: '合同文件', summary: '采购合同与附件翻译，要求保留条款结构并标注疑义内容。' },
  { id: 'biz-06', title: '农产品贸易洽谈', pair: '中文 ↔ 越南语', service: 'interpretation', mode: '线上/线下', location: '广西·崇左', schedule: '日期待定', industry: '农产品', summary: '供货、包装、物流和验收环节沟通，需要熟悉跨境贸易表达。' },
  { id: 'biz-07', title: '网站与小程序本地化', pair: '中文 → 越南语', service: 'technical', mode: '线上', location: '不限地区', schedule: '分批交付', industry: '互联网', summary: '界面文案、帮助中心和营销页面本地化，需兼顾术语与用户习惯。' },
  { id: 'biz-08', title: '线上培训实时口译', pair: '中文 → 越南语', service: 'simultaneous', mode: '线上', location: '远程', schedule: '约 2 小时', industry: '企业培训', summary: '线上产品培训需要实时口译，提前提供术语表和演示材料。' },
  { id: 'biz-09', title: '物流仓储现场沟通', pair: '中文 ↔ 越南语', service: 'escort', mode: '线下', location: '越南·海防', schedule: '1 天', industry: '物流仓储', summary: '仓储流程、装卸安排和现场安全沟通，需要陪同口译。' },
  { id: 'biz-10', title: '企业宣传资料越南语版', pair: '中文 → 越南语', service: 'translation', mode: '线上', location: '不限地区', schedule: '按字数评估', industry: '品牌宣传', summary: '公司介绍、产品手册和宣传文案翻译，重视越南语表达自然度。' },
  { id: 'biz-11', title: '工程项目技术会议', pair: '中文 ↔ 越南语', service: 'technical', mode: '线上/线下', location: '越南·胡志明市', schedule: '长期协作', industry: '工程技术', summary: '项目进度、图纸和施工方案沟通，优先有工程领域经验的译员。' },
  { id: 'biz-12', title: '短视频字幕翻译', pair: '中文 → 越南语', service: 'translation', mode: '线上', location: '远程', schedule: '持续更新', industry: '跨境电商', summary: '商品短视频字幕与标题本地化，要求简洁、口语化并符合平台语境。' }
];

function decorateActive(item) {
  return Object.assign({}, item, {
    title: `${SERVICE_LABELS[item.service_type] || '翻译'}业务需求`,
    pair: `${LANGUAGE_LABELS[item.source_lang] || item.source_lang} → ${LANGUAGE_LABELS[item.target_lang] || item.target_lang}`,
    service: item.service_type,
    serviceLabel: SERVICE_LABELS[item.service_type] || item.service_type,
    mode: item.service_mode === 'offline' ? '线下' : (item.service_mode === 'both' ? '线上/线下' : '线上'),
    location: item.city || '不限地区',
    schedule: item.service_at ? String(item.service_at).slice(0, 10) : '时间可商议',
    industry: '当前需求',
    summary: item.note,
    statusLabel: '当前需求',
    is_example: false
  });
}

function decorateExample(item) {
  return Object.assign({}, item, {
    serviceLabel: SERVICE_LABELS[item.service] || item.service,
    statusLabel: '历史脱敏示例',
    is_example: true
  });
}

Page({
  data: {
    loading: true,
    notice: '',
    activeItems: [],
    exampleItems: EXAMPLE_BUSINESSES.map(decorateExample),
    visibleExamples: EXAMPLE_BUSINESSES.map(decorateExample),
    filter: '',
    respondingId: '',
    filters: [
      { code: '', label: '全部' }, { code: 'interpretation', label: '口译' },
      { code: 'translation', label: '笔译' }, { code: 'escort', label: '陪同' },
      { code: 'simultaneous', label: '同传' }, { code: 'technical', label: '技术' }
    ]
  },

  onLoad() {
    if (wx.showShareMenu) wx.showShareMenu({ menus: ['shareAppMessage', 'shareTimeline'] });
  },
  onShow() { this.loadBusinesses(); },
  onPullDownRefresh() { this.loadBusinesses().finally(() => wx.stopPullDownRefresh()); },

  async loadBusinesses() {
    this.setData({ loading: true, notice: '' });
    try {
      await app.login();
      const result = await directoryApi.listMatchedNeeds();
      this.setData({ activeItems: (result.items || []).map(decorateActive), loading: false });
    } catch (err) {
      this.setData({ activeItems: [], loading: false, notice: '完善译员资料后，可在这里看到与你匹配的当前业务。' });
    }
  },

  onFilter(e) {
    const filter = e.currentTarget.dataset.code || '';
    const visibleExamples = this.data.exampleItems.filter((item) => !filter || item.service === filter);
    this.setData({ filter, visibleExamples });
  },

  onPublish() {
    wx.navigateTo({ url: '/pages/business-publish/business-publish' });
  },

  async onRespond(e) {
    const id = e.currentTarget.dataset.id;
    if (!id || this.data.respondingId) return;
    this.setData({ respondingId: id });
    try {
      await directoryApi.respondToNeed(id);
      wx.showToast({ title: '已表示愿意联系', icon: 'success' });
      await this.loadBusinesses();
    } catch (err) {
      wx.showToast({ title: (err && err.message) || '响应失败', icon: 'none' });
    } finally {
      this.setData({ respondingId: '' });
    }
  },

  onShareAppMessage() {
    return { title: '悦迅翻译｜中越翻译业务信息', path: '/pages/ask/ask' };
  },
  onShareTimeline() { return { title: '悦迅翻译｜中越翻译业务信息' }; }
});

module.exports = { EXAMPLE_BUSINESSES, decorateActive };
