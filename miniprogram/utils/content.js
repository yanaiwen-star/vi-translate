// utils/content.js — 拉取官网/小程序共用的内容（来自 ECS 后端 /api/content）
// 与官网同源：在服务器改一处，小程序和官网同步更新。
const { request } = require('./api.js');

let _cache = null;

// 本地兜底：服务器不可达时仍保证页面有内容
const DEFAULTS = {
  company: {
    name: '南宁市悦迅翻译有限公司',
    slogan: '专注于越南语翻译服务的公司',
    stats: [
      { num: '14', unit: '年', label: '深耕越南语' },
      { num: '100', unit: '+', label: '专业译员' },
      { num: '20', unit: '+', label: '支持语种' }
    ]
  },
  contact: {
    phone: '13077711058',
    wechat: '39446846',
    email: '39446846@qq.com',
    address: '广西民族大学北门相思湖畔A区商铺206',
    latitude: 22.836,
    longitude: 108.256
  },
  homeQuick: [
    { id: 'si', icon: '🎙️', name: '越南语同声传译', desc: '会议 · 论坛 · 商务实时同传' },
    { id: 'ot', icon: '🤝', name: '越南语陪同口译', desc: '考察 · 谈判 · 现场随行' },
    { id: 'tr', icon: '📄', name: '越南语笔译', desc: '合同 · 标书 · 证件文书' },
    { id: 'ai', icon: '🤖', name: 'AI 实时同传', desc: '悦迅自研 · 中越双向自动' }
  ],
  advantages: [
    { icon: '🏆', title: '14 年越南语基因', desc: '自 2011 年起只做越南语，积累深厚语料与译员资源。' },
    { icon: '⚡', title: '独家 AI 同传工具', desc: '自研中越同传引擎，会议、商务场景即开即用。' },
    { icon: '🎯', title: '专注越南语翻译', desc: '不被大而全稀释，越南语才是我们的专业主场。' }
  ],
  services: [
    { icon: '🎙️', name: '越南语同声传译', desc: '国际会议、论坛峰会、商务洽谈的中越/越中实时同传，配备资深同传译员与设备方案。', tags: ['会议同传', '论坛峰会', '商务洽谈'] },
    { icon: '🤝', name: '越南语陪同口译', desc: '展会考察、工厂验厂、商务谈判、旅游接待等现场随行口译，反应快、懂行业。', tags: ['展会考察', '商务谈判', '现场随行'] },
    { icon: '📄', name: '越南语笔译', desc: '合同标书、法律文书、产品资料、证件公证等专业笔译，母语级审校，术语统一。', tags: ['合同标书', '法律文书', '证件公证'] },
    { icon: '🌐', name: '网站/软件本地化', desc: '网站、App、小程序、宣传物料的越南语本地化，兼顾语言准确与文化适配。', tags: ['网站', 'App', '宣传物料'] },
    { icon: '🤖', name: 'AI 实时同传', desc: '悦迅自研中越双向 AI 同传工具，自动识别语种、即说即译、语音播报，成本更低。', tags: ['中越双向', '自动识别', '语音播报'] },
    { icon: '🗺️', name: '多语种翻译', desc: '以越南语为核心，同时提供越—英、越—中、中—英等 20+ 语种翻译服务。', tags: ['越—英', '越—中', '20+ 语种'] }
  ],
  about: {
    credentials: ['中央民族语文翻译局', '中央人民广播电台越语部', '中国国际广播电台越语部', '中央民族大学越南语专业', '北京大学东方语言学系']
  }
};

async function fetchContent(force = false) {
  if (_cache && !force) return _cache;
  try {
    const data = await request('GET', '/api/content', null, false);
    _cache = Object.assign({}, DEFAULTS, data);
    return _cache;
  } catch (e) {
    console.warn('内容拉取失败，使用本地兜底', e);
    return _cache || DEFAULTS;
  }
}

module.exports = { fetchContent, DEFAULTS };
