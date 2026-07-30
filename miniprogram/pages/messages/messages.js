const scenes = require('./phrases.js');

const AUDIO_BASE = 'https://yuexunfanyi.com/static/phrases';
const sceneOptions = [{ id: 'all', name: '全部场景', icon: '▦' }].concat(
  scenes.map((scene) => ({ id: scene.id, name: scene.name, icon: scene.icon }))
);

Page({
  data: {
    scenes,
    sceneOptions,
    visibleScenes: scenes,
    activeScene: 'all',
    activeSceneIndex: 0,
    activeSceneLabel: '▦  全部场景',
    keyword: '',
    playingKey: '',
    audioLoading: false
  },

  onLoad() {
    this.audio = null;
  },

  onUnload() {
    this.disposeAudio();
  },

  disposeAudio() {
    const audio = this.audio;
    // 先解除当前引用，旧实例随后触发的 onStop/onError 就会被忽略。
    this.audio = null;
    if (!audio) return;
    try { audio.stop(); } catch (e) {}
    try { audio.destroy(); } catch (e) {}
  },

  createAudio(key) {
    const audio = wx.createInnerAudioContext();
    this.audio = audio;
    audio.obeyMuteSwitch = false;
    const isCurrent = () => this.audio === audio && this.data.playingKey === key;
    audio.onPlay(() => {
      if (isCurrent()) this.setData({ audioLoading: false });
    });
    audio.onEnded(() => {
      if (isCurrent()) this.setData({ playingKey: '', audioLoading: false });
    });
    audio.onStop(() => {
      if (isCurrent()) this.setData({ playingKey: '', audioLoading: false });
    });
    audio.onError(() => {
      if (!isCurrent()) return;
      this.setData({ playingKey: '', audioLoading: false });
      wx.showToast({ title: '语音加载失败，请检查网络', icon: 'none' });
    });
    return audio;
  },

  onSceneChange(e) {
    const index = Number(e.detail.value) || 0;
    const selected = sceneOptions[index];
    this.setData({
      activeScene: selected.id,
      activeSceneIndex: index,
      activeSceneLabel: `${selected.icon}  ${selected.name}`
    }, () => this.applyFilter());
  },

  onSearch(e) {
    this.setData({ keyword: (e.detail.value || '').trim() }, () => this.applyFilter());
  },

  clearSearch() {
    this.setData({ keyword: '' }, () => this.applyFilter());
  },

  applyFilter() {
    const { activeScene, keyword } = this.data;
    const query = keyword.toLowerCase();
    const visibleScenes = scenes
      .filter((scene) => activeScene === 'all' || scene.id === activeScene)
      .map((scene) => ({
        ...scene,
        items: scene.items.filter((item) => !query
          || item.zh.includes(query)
          || item.vi.toLowerCase().includes(query))
      }))
      .filter((scene) => scene.items.length > 0);
    this.setData({ visibleScenes });
  },

  playPhrase(e) {
    const { id, lang } = e.currentTarget.dataset;
    const key = `${id}-${lang}`;
    if (this.data.playingKey === key) {
      this.disposeAudio();
      this.setData({ playingKey: '', audioLoading: false });
      return;
    }
    this.disposeAudio();
    this.setData({ playingKey: key, audioLoading: true });
    const audio = this.createAudio(key);
    const extension = lang === 'vi' ? 'wav' : 'mp3';
    audio.src = `${AUDIO_BASE}/${key}.${extension}`;
    audio.play();
  }
});
