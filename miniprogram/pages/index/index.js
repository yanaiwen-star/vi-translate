// pages/index/index.js
// 同传主页面 —— 复用网页版 Qwen 系统（底层 DashScope realtime）
// 界面与功能对齐 www.yuexunfanyi.com 的「实时同传手机版」：
//   双面板（原文 / 译文）、开始 / 停止连续录音、拍照翻译、
//   源语言 / 目标语言 / 区域 / 发音人 / 语音输出 / 声音克隆、音量条、记录回放

const { RecorderManager } = require('../../utils/recorder.js');
const { LiveTranslate } = require('../../utils/live.js');
const sessionUtil = require('../../utils/session.js');

const app = getApp();

// 语言列表（与后端 LANGUAGES 校验一致；target 不接受 auto）
const LANGS = [
  { code: 'auto', label: '自动检测' },
  { code: 'zh', label: '中文' },
  { code: 'vi', label: '越南语' },
  { code: 'en', label: '英语' },
  { code: 'ja', label: '日语' },
  { code: 'ko', label: '韩语' },
  { code: 'th', label: '泰语' },
  { code: 'fr', label: '法语' },
  { code: 'ru', label: '俄语' },
  { code: 'de', label: '德语' },
  { code: 'es', label: '西班牙语' }
];
const REGIONS = [
  { code: 'mainland', label: '中国大陆' },
  { code: 'intl', label: '新加坡 / 国际' }
];
const VOICES = ['Tina', 'Cindy', 'Raymond', 'Ethan', 'Serena', 'Mia', 'Qiao', 'Sunny', 'Angel', 'Harvey', 'Mione', 'Kiki'];
const VOICE_CLONE_MODES = [
  { code: 'off', label: '关' },
  { code: 'once', label: '单角色克隆' },
  { code: 'always', label: '多角色克隆' }
];

const MODEL_NAME = 'qwen3.5-livetranslate-flash-realtime';

// 拍照翻译后端（自己的服务器，与实时同传同一域名 yuexunfanyi.com）
const PHOTO_TRANSLATE_URL = 'https://yuexunfanyi.com/photo-translate';
// 文本翻译后端（手动输入文字翻译，同域名）
const TEXT_TRANSLATE_URL = 'https://yuexunfanyi.com/text-translate';

Page({
  data: {
    mode: 'voice',
    running: false,
    photoLoading: false,
    statusText: '待机',
    statusState: 'idle',

    // 拍照翻译结果
    photoSource: '',
    photoTranslation: '',
    photoSourceIndex: 0,   // auto（拍照独立语种，不影响语音同传）
    photoTargetIndex: 0,   // zh（默认翻成中文）

    // 文本翻译（手动输入文字）
    textInput: '',
    textTranslation: '',
    textLoading: false,
    textSourceIndex: 0,    // auto
    textTargetIndex: 0,    // zh

    // 双面板文本
    sourceLines: [],
    sourceDraft: '',
    translationLines: [],
    translationDraft: '',

    // 音量条
    levelPct: 0,

    // 控制项
    sourceLangs: LANGS,
    targetLangs: LANGS.filter((l) => l.code !== 'auto'),
    regions: REGIONS,
    voices: VOICES,
    voiceCloneModes: VOICE_CLONE_MODES,
    sourceIndex: 1,    // zh（LANGS[1]，默认中文）
    targetIndex: 1,    // vi（targetLangs[1] —— targetLangs 已滤掉 auto，默认越南语）
    regionIndex: 0,    // mainland
    voiceIndex: 0,     // Tina
    voiceCloneIndex: 0, // off
    audioEnabled: true,

    // —— 面对面模式（双话筒·一人一句 PTT，内联；复用 this.live/this.recorder）——
    faceLangOptions: LANGS.filter((l) => l.code !== 'auto'),
    faceMyIndex: 0,      // 默认我说中文
    faceMyLang: 'zh',
    faceMyLabel: '中文',
    facePeerIndex: 1,    // 默认对方越南语
    facePeerLang: 'vi',
    facePeerLabel: '越南语',
    faceShowSettings: false,
    faceActiveSide: '',  // '' | 'mine' | 'peer'
    faceRecording: false,
    faceFinalizing: false,
    faceTurns: [],       // [{id, side, src, tgt}]
    faceCur: { side: '', src: '', tgt: '' },
    faceCurActive: false,
    faceTick: 0,
    faceTopView: '',
    faceBottomView: '',

    // 底部信息
    metrics: 'Model: ' + MODEL_NAME
  },

  recorder: null,
  live: null,
  sessionStart: 0,
  // 译文 TTS 播放门控（半双工，防回声自激环路）
  ttsPlaying: false,
  ttsTailTimer: null,
  audioQueue: [],
  playingAudio: null,
  lastWavB64: '',

  // 面对面模式实例状态
  faceTurnSeq: 0,
  faceCurrentTurnId: '',
  faceCurSide: '',
  faceFinalizingTimer: null,
  faceCommittedSrc: '',
  faceLiveSrc: '',
  faceCommittedTgt: '',
  faceLiveTgt: '',

  // —— 文本状态（对齐网页版 app.js）——
  sourceHistory: [],
  sourceDraft: '',
  lastSourceFinal: '',
  lastSourcePartial: '',
  translationHistory: [],
  translationDraft: '',
  lastTranslationFinal: '',
  lastTranslationPartial: '',

  onLoad() {
    // 防御性再设一次 iOS 音频会话解锁（主设置在 app.js onLaunch，这里兜底，
    // 防止某些基础库版本下全局设置未生效导致同传语音不响）。
    if (wx.setInnerAudioOption) {
      wx.setInnerAudioOption({ obeyMuteSwitch: false, mixWithOther: true });
    }

    this.recorder = new RecorderManager();
    this.recorder.init({ mode: 'pcm', duration: 0 });
    this.recorder.onProgress = (info) => {
      if (this.ttsPlaying) return;   // TTS 播放时麦克风静默，音量条不跳动
      this.setData({ levelPct: Math.min(100, info.volume || 0) });
    };
    this.recorder.onFrame = (frame) => {
      // iPhone 扬声器全双工易自激，译文播放时仍屏蔽麦克风上送（防回声环路）。
      // 单句内录音已是逐帧流式上传，边听边译的"边"由录音帧粒度决定（见 recorder.js）。
      if (this.ttsPlaying) return;
      if (this.live && this.live.connected) {
        this.live.sendAudioFrame(frame);
      }
    };
    this.recorder.onStop = (res) => {
      const seconds = Math.ceil((res.duration || 0) / 1000);
      if (seconds > 0) {
        app.updateQuota(seconds);
      }
    };
    this.recorder.onError = (err) => {
      console.error('recorder error', err);
      if (this.data.mode === 'face') this.faceAbortTurn('录音失败，请重试');
      else this.stopSession('录音失败，请重试');
    };

    sessionUtil.ensureSession();
    this.checkRecordPermission();

    // 面对面模式：读取持久化的双语种
    try {
      const my = wx.getStorageSync('face_my_lang');
      const peer = wx.getStorageSync('face_peer_lang');
      if (my && peer) this.faceApplyLangs(my, peer);
    } catch (e) {}
  },

  onUnload() {
    this.teardownSession();
    if (this.faceFinalizingTimer) { clearTimeout(this.faceFinalizingTimer); this.faceFinalizingTimer = null; }
    if (this.playingAudio) { try { this.playingAudio.destroy(); } catch (e) {} }
    if (this.ttsTailTimer) { clearTimeout(this.ttsTailTimer); this.ttsTailTimer = null; }
    this.ttsPlaying = false;
    this.audioQueue = [];
  },

  onHide() {
    // 离开页面时若在面对面录音，先收尾
    if (this.data.mode === 'face' && this.data.faceActiveSide) this.faceEndTurn(this.data.faceActiveSide);
  },

  async checkRecordPermission() {
    try {
      const res = await wx.getSetting();
      if (!res.authSetting['scope.record']) {
        await wx.authorize({ scope: 'scope.record' });
      }
    } catch (err) {
      console.warn('麦克风权限未授权', err);
      this.setData({ statusText: '请授权麦克风权限' });
    }
  },

  // —— 模式切换（同传 / 面对面 / 拍照翻译 / 文字翻译，全部内联）——
  onSetMode(e) {
    const mode = e.currentTarget.dataset.mode;
    if (mode === this.data.mode) return;
    // 离开当前模式前，停掉进行中的会话（语音同传 / 面对面回合）
    if (this.data.running) this.stopSession();
    if (this.data.faceActiveSide) this.faceAbortTurn();
    this.setData({ mode });
  },

  // —— 控制项变更 ——
  onSourceLang(e) {
    if (this.data.running) return;
    this.setData({ sourceIndex: Number(e.detail.value) });
  },
  onTargetLang(e) {
    if (this.data.running) return;
    this.setData({ targetIndex: Number(e.detail.value) });
  },
  onRegion(e) {
    if (this.data.running) return;
    this.setData({ regionIndex: Number(e.detail.value) });
  },
  onVoice(e) {
    if (this.data.running) return;
    this.setData({ voiceIndex: Number(e.detail.value) });
  },
  onVoiceClone(e) {
    if (this.data.running) return;
    this.setData({ voiceCloneIndex: Number(e.detail.value) });
  },
  onToggleAudio(e) {
    if (this.data.running) return;
    this.setData({ audioEnabled: e.detail.value });
  },

  // —— 拍照翻译：独立语种选择 ——
  onPhotoSourceLang(e) {
    this.setData({ photoSourceIndex: Number(e.detail.value) });
  },
  onPhotoTargetLang(e) {
    this.setData({ photoTargetIndex: Number(e.detail.value) });
  },

  // —— 文本翻译：独立语种选择 + 输入 ——
  onTextSourceLang(e) {
    this.setData({ textSourceIndex: Number(e.detail.value) });
  },
  onTextTargetLang(e) {
    this.setData({ textTargetIndex: Number(e.detail.value) });
  },
  onTextInput(e) {
    this.setData({ textInput: e.detail.value });
  },
  onClearText() {
    this.setData({ textInput: '', textTranslation: '' });
  },

  async onTextTranslate() {
    if (this.data.textLoading) return;
    const text = (this.data.textInput || '').trim();
    if (!text) {
      wx.showToast({ title: '请输入要翻译的文字', icon: 'none' });
      return;
    }
    this.setData({ textLoading: true, statusText: '翻译中...', statusState: 'warn' });
    try {
      const res = await new Promise((resolve, reject) => {
        wx.request({
          url: TEXT_TRANSLATE_URL,
          method: 'POST',
          timeout: 60000,
          header: { 'Content-Type': 'application/json' },
          data: {
            text,
            sourceLang: this.data.sourceLangs[this.data.textSourceIndex].code,
            targetLang: this.data.targetLangs[this.data.textTargetIndex].code
          },
          success: resolve,
          fail: reject
        });
      });
      const r = res.data || {};
      if (r.code === 0 && r.data) {
        this.setData({
          textTranslation: r.data.translation || '',
          statusText: '文本翻译完成',
          statusState: 'idle'
        });
      } else {
        wx.showToast({ title: r.message || '翻译失败', icon: 'none' });
        this.setData({ statusText: '待机', statusState: 'idle' });
      }
    } catch (e) {
      console.error('text-translate error', e);
      wx.showToast({ title: '请求失败，请重试', icon: 'none' });
      this.setData({ statusText: '待机', statusState: 'idle' });
    } finally {
      this.setData({ textLoading: false });
    }
  },

  // —— 开始 / 停止 ——
  async onStart() {
    if (this.data.running) return;
    // 半拦：已登录但没设昵称的用户必须先设昵称才能发起同传。
    // 匿名用户（未登录，token 为空）跳过此检查。
    const hasToken = (app.globalData && app.globalData.accessToken) || wx.getStorageSync('access_token');
    if (hasToken && !app.ensureNickname({ from: 'live', reason: '发起同传前请先设置昵称' })) {
      return;
    }
    // 清理上一次未正常关闭的会话（防泄漏并发名额：热重载/重复点击导致旧 ws 孤立）
    if (this.live) {
      try { this.live.close(); } catch (e) {}
      this.live = null;
    }
    if (this.recorder && this.recorder.isRecording) {
      try { this.recorder.stop(); } catch (e) {}
    }
    if (!(await app.checkQuota())) {
      wx.showModal({
        title: '同传时长已用完',
        content: '同传时长已用完，可购买语音包继续使用',
        showCancel: false
      });
      return;
    }
    this.resetTextState(
      '等待麦克风权限...',
      '等待翻译...'
    );
    this.setData({ mode: 'voice', running: true, statusText: '连接中...', statusState: 'warn', levelPct: 0 });

    const token = (app.globalData && app.globalData.accessToken) || '';
    const sourceLang = this.data.sourceLangs[this.data.sourceIndex].code;
    const targetLang = this.data.targetLangs[this.data.targetIndex].code;
    const region = this.data.regions[this.data.regionIndex].code;
    const voice = this.data.voices[this.data.voiceIndex];
    const voiceCloneMode = this.data.voiceCloneModes[this.data.voiceCloneIndex].code;

    this.live = new LiveTranslate({
      token,
      sourceLang,
      targetLang,
      region,
      audioEnabled: this.data.audioEnabled,
      voice,
      voiceCloneMode,
      onMessage: (m) => this.handleLiveMessage(m),
      onReady: (msg) => this.onServerReady(msg, targetLang),
      onError: (err) => {
        console.error('live error', err);
        this.stopSession('出错了：' + (err.message || '未知错误'));
      }
    });

    try {
      await this.live.connect();
      this.sessionStart = Date.now();
      wx.vibrateShort({ type: 'light' });
      this.recorder.start();
    } catch (err) {
      console.error('connect fail', err);
      this.stopSession('连接失败：' + (err.message || '网络错误'));
    }
  },

  onServerReady(msg, targetLang) {
    const audioLabel = msg.audio_enabled ? ' · 语音输出' : ' · 仅文字';
    this.setData({
      statusText: '聆听中',
      statusState: 'active',
      metrics: `${msg.source_language || 'auto'} -> ${targetLang}${audioLabel}`
    });
  },

  onStop() {
    if (!this.data.running) return;
    this.stopSession();
  },

  // 真正结束一轮会话
  stopSession(statusText) {
    // voice 模式：立即 close（不 finish），按测试 audio-dedup test 21 顺序
    // calls = ['close', 'recorder.stop', 'audio.stop']
    if (this.live) {
      try { this.live.close(); } catch (e) {}
      this.live = null;
    }
    if (this._draftCommitTimer) { clearTimeout(this._draftCommitTimer); this._draftCommitTimer = null; }
    this.audioPcmBuffer = [];
    if (this.recorder) { try { this.recorder.stop(); } catch (e) {} }
    this.stopAudioPlayback();
    this.setData({
      running: false,
      statusText: statusText || '已停止',
      statusState: 'idle',
      levelPct: 0
    });
  },

  stopAudioPlayback() {
    this.audioQueue = [];
    if (this.playingAudio) { try { this.playingAudio.destroy(); } catch (e) {} this.playingAudio = null; }
    this.ttsPlaying = false;
    if (this.ttsTailTimer) { clearTimeout(this.ttsTailTimer); this.ttsTailTimer = null; }
  },

  teardownSession() {
    if (this.live) { try { this.live.close(); } catch (e) {} this.live = null; }
    if (this.recorder) this.recorder.destroy();
  },

  // —— 处理服务器下行消息（与网页版 handleServerMessage 对齐）——
  handleLiveMessage(m) {
    if (m.type === 'model_audio_wav') {
      // 同传模式以服务器下发的整段 WAV 作为译文语音：model_audio 流式 PCM 在 iOS 上
      // 由客户端拼出的 WAV 不发声（采样率/格式对齐问题），故以服务器完整 WAV 为准、必定可播；
      // 同时跳过 model_audio 避免同句双播。面对面模式由 handleFaceMessage 处理，这里不接。
      if (this.data.mode === 'face') return;
      this.enqueueAudio(m.audio);
      return;
    }
    if (m.type === 'model_audio') {
      // 流式 PCM 语音路径暂不可用（iOS 客户端拼 WAV 不发声），跳过以免与整段 WAV 双播；
      // 待录音方案改造、确认能稳定出声后再启用。
      return;
    }
    if (m.type !== 'model_event') return;

    if (m.status === 'connected') this.setData({ statusText: '已连接', statusState: 'active' });
    if (m.status === 'translating') this.setData({ statusText: '翻译中...', statusState: 'warn' });
    if (m.status === 'listening') this.setData({ statusText: '聆听中', statusState: 'active' });

    if (m.response_started) {
      this.translationDraft = '';
      this.lastTranslationPartial = '';
      this.renderTranslation();
    }
    if (m.response_done) {
      if (this.translationDraft) this.commitFinal('translation', this.translationDraft);
    }
    if (m.source_partial) this.updateDraft('source', m.source_partial);
    if (m.source_final) this.commitFinal('source', m.source_final);
    if (m.translation_partial) this.updateDraft('translation', m.translation_partial);
    if (m.translation_final) this.commitFinal('translation', m.translation_final);
    if (m.usage) this.addUsage(m.usage);
  },

  // —— 文本渲染（对齐网页版 renderPanel / updateDraft / commitFinal）——
  normalizeText(text) {
    return String(text || '').replace(/\s+/g, ' ').trim();
  },

  updateDraft(kind, text) {
    const next = this.normalizeText(text);
    if (!next) return;
    if (kind === 'source') {
      if (next === this.lastSourcePartial) return;
      this.sourceDraft = next;
      this.lastSourcePartial = next;
      this.renderSource();
      this.scheduleDraftCommit('source');
      return;
    }
    if (next === this.lastTranslationPartial) return;
    this.translationDraft = next;
    this.lastTranslationPartial = next;
    this.renderTranslation();
    this.scheduleDraftCommit('translation');
  },

  // 修复「实时只输出一句，其他就消失」—— 集成的 DashScope 流式 ASR
  // 在说话间隔时不再推 partial，也不推 final，导致上一句的 draft 永远
  // 停在屏上，下一句 partial 来了才覆盖。给 draft 加 1.5s 自动 commit：
  // 用户停止说话 1.5s 后把 draft 当 final 落 library，不再「消失」。
  scheduleDraftCommit(kind) {
    if (this._draftCommitTimer) clearTimeout(this._draftCommitTimer);
    this._draftCommitTimer = setTimeout(() => {
      this._draftCommitTimer = null;
      if (kind === 'source' && this.sourceDraft) {
        this.commitFinal('source', this.sourceDraft);
      } else if (kind === 'translation' && this.translationDraft) {
        this.commitFinal('translation', this.translationDraft);
      }
    }, 1500);
  },

  commitFinal(kind, text) {
    const finalText = this.normalizeText(text);
    if (!finalText) return;
    if (this._draftCommitTimer) { clearTimeout(this._draftCommitTimer); this._draftCommitTimer = null; }
    if (kind === 'source') {
      if (finalText === this.lastSourceFinal) {
        this.sourceDraft = '';
        this.lastSourcePartial = '';
        this.renderSource();
        return;
      }
      if (!this.sourceHistory.includes(finalText)) this.sourceHistory.push(finalText);
      this.lastSourceFinal = finalText;
      this.sourceDraft = '';
      this.lastSourcePartial = '';
      this.renderSource();
      this.persistPair();
      return;
    }
    if (finalText === this.lastTranslationFinal) return;
    if (!this.translationHistory.includes(finalText)) this.translationHistory.push(finalText);
    this.lastTranslationFinal = finalText;
    this.translationDraft = '';
    this.lastTranslationPartial = '';
    this.renderTranslation();
  },

  renderSource() {
    const lines = this.sourceHistory.slice();
    this.setData({ sourceLines: lines, sourceDraft: this.sourceDraft });
  },
  renderTranslation() {
    const lines = this.translationHistory.slice();
    this.setData({ translationLines: lines, translationDraft: this.translationDraft });
  },

  resetTextState(sourceMsg, translationMsg) {
    if (this._draftCommitTimer) { clearTimeout(this._draftCommitTimer); this._draftCommitTimer = null; }
    this.sourceHistory = [];
    this.sourceDraft = '';
    this.lastSourceFinal = '';
    this.lastSourcePartial = '';
    this.translationHistory = [];
    this.translationDraft = '';
    this.lastTranslationFinal = '';
    this.lastTranslationPartial = '';
    this.setData({
      sourceLines: [],
      sourceDraft: '',
      translationLines: [],
      translationDraft: ''
    });
  },

  addUsage(usage) {
    if (!usage || typeof usage !== 'object') return;
    // 仅用于体验展示，可在 metrics 中追加（保持简洁，这里不显示 token）
  },

  // 配对保存一句话到服务器历史
  persistPair() {
    const src = this.lastSourceFinal;
    const tgt = this.lastTranslationFinal;
    if (!src || !tgt) return;
    const targetLang = this.data.targetLangs[this.data.targetIndex].code;
    const sourceLang = this.data.sourceLangs[this.data.sourceIndex].code;
    sessionUtil.ensureSession().then((sid) => {
      sessionUtil.saveMessage({
        sessionId: sid,
        sourceLang,
        sourceText: src,
        targetLang,
        targetText: tgt,
        audioDuration: 0
      });
    });
    this.lastSourceFinal = '';
    this.lastTranslationFinal = '';
  },

  // —— 流式 PCM 累积播放（处理 DashScope 的 model_audio delta，对齐网页版 AudioContext 流式播放）——
  enqueuePcmAudio(b64) {
    if (!this.data.audioEnabled || !b64) return;
    try {
      const u8 = new Uint8Array(wx.base64ToArrayBuffer(b64));
      this.audioPcmBuffer.push(u8);
    } catch (e) { return; }
    if (!this.audioFlushTimer) {
      this.audioFlushTimer = setTimeout(() => this.flushPcmAudio(), 220);
    }
  },

  flushPcmAudio() {
    this.audioFlushTimer = null;
    if (!this.audioPcmBuffer.length) return;
    let total = 0;
    for (const p of this.audioPcmBuffer) total += p.byteLength;
    const merged = new Uint8Array(total);
    let off = 0;
    for (const p of this.audioPcmBuffer) { merged.set(p, off); off += p.byteLength; }
    this.audioPcmBuffer = [];

    const sampleRate = this.audioSampleRate || 24000;
    const dataLen = merged.byteLength;
    const buf = new ArrayBuffer(44 + dataLen);
    const view = new DataView(buf);
    const writeStr = (o, s) => { for (let i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i)); };
    writeStr(0, 'RIFF');
    view.setUint32(4, 36 + dataLen, true);
    writeStr(8, 'WAVE');
    writeStr(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeStr(36, 'data');
    view.setUint32(40, dataLen, true);
    new Uint8Array(buf, 44).set(merged);

    const fs = wx.getFileSystemManager();
    const path = `${wx.env.USER_DATA_PATH}/pcm_${Date.now()}_${Math.floor(Math.random() * 1e4)}.wav`;
    fs.writeFile({
      filePath: path,
      data: buf,
      success: () => {
        this.audioQueue.push(path);
        this.playNextAudio();
      },
      fail: (e) => console.warn('pcm wav write fail', e)
    });
  },

  // —— 译文语音（逐句 WAV 实时播放）——
  // audioQueue 元素统一为 {path}（同传语音逐句入队播放）
  enqueueAudio(b64, force) {
    this.lastWavB64 = b64;
    if (!this.data.audioEnabled && !force) return;
    const fs = wx.getFileSystemManager();
    const path = `${wx.env.USER_DATA_PATH}/tts_${Date.now()}_${Math.floor(Math.random() * 1e4)}.wav`;
    const buffer = wx.base64ToArrayBuffer(b64);
    fs.writeFile({
      filePath: path,
      data: buffer,
      success: () => {
        this.audioQueue.push(path);
        this.playNextAudio();
      },
      fail: (e) => console.warn('wav write fail', e)
    });
  },

  playNextAudio() {
    if (this.playingAudio || !this.audioQueue.length) return;
    const item = this.audioQueue.shift();
    const path = typeof item === 'string' ? item : item.path;
    const audio = wx.createInnerAudioContext();
    this.playingAudio = audio;
    this.ttsPlaying = true;
    if (this.ttsTailTimer) { clearTimeout(this.ttsTailTimer); this.ttsTailTimer = null; }
    this.setData({ levelPct: 0 });
    audio.src = path;
    audio.obeyMuteSwitch = false;
    const onDone = () => {
      try { audio.destroy(); } catch (e) {}
      this.playingAudio = null;
      try { wx.getFileSystemManager().unlink({ filePath: path }); } catch (e) {}
      if (this.audioQueue.length) {
        this.playNextAudio();
      } else if (!this.data.running) {
        this.ttsPlaying = false;
      } else {
        if (this.ttsTailTimer) clearTimeout(this.ttsTailTimer);
        this.ttsTailTimer = setTimeout(() => {
          this.ttsPlaying = false;
          this.ttsTailTimer = null;
        }, 350);
      }
    };
    audio.onEnded(onDone);
    audio.onError((e) => { console.warn('audio play err', e); onDone(); });
    if (audio.onPlay) audio.onPlay(() => { console.log('[audio] play started, path=', path); });
    if (audio.onCanplay) audio.onCanplay(() => { console.log('[audio] canplay, path=', path); });
    audio.play();
  },

  // —— 清空 ——
  onClear() {
    if (this.data.running) {
      wx.showModal({ title: '提示', content: '同传进行中，请先停止', showCancel: false });
      return;
    }
    this.resetTextState('点击「开始」后，对着麦克风说话。', '译文将显示在这里。');
    app.globalData.currentSessionId = null;
    sessionUtil.ensureSession();
    this.setData({ metrics: 'Model: ' + MODEL_NAME });
  },

  // ===== 面对面模式（双话筒·一人一句 PTT） =====
  // 复用 this.live / this.recorder / TTS 播放；同一时刻只激活一个话筒。
  faceApplyLangs(myCode, peerCode) {
    const opts = this.data.faceLangOptions;
    const myIdx = Math.max(0, opts.findIndex((l) => l.code === myCode));
    const peerIdx = Math.max(0, opts.findIndex((l) => l.code === peerCode));
    this.setData({
      faceMyIndex: myIdx, faceMyLang: opts[myIdx].code, faceMyLabel: opts[myIdx].label,
      facePeerIndex: peerIdx, facePeerLang: opts[peerIdx].code, facePeerLabel: opts[peerIdx].label
    });
  },
  onFaceSwapLangs() {
    const newMy = this.data.facePeerLang;
    const newPeer = this.data.faceMyLang;
    this.faceApplyLangs(newMy, newPeer);
    wx.setStorageSync('face_my_lang', newMy);
    wx.setStorageSync('face_peer_lang', newPeer);
  },
  onFaceChangeMyLang(e) {
    const idx = Number(e.detail.value);
    this.faceApplyLangs(this.data.faceLangOptions[idx].code, this.data.facePeerLang);
    wx.setStorageSync('face_my_lang', this.data.faceLangOptions[idx].code);
  },
  onFaceChangePeerLang(e) {
    const idx = Number(e.detail.value);
    this.faceApplyLangs(this.data.faceMyLang, this.data.faceLangOptions[idx].code);
    wx.setStorageSync('face_peer_lang', this.data.faceLangOptions[idx].code);
  },

  onFaceMicDown(e) {
    const side = e.currentTarget.dataset.side;
    if (this.data.faceActiveSide) return;  // 互斥：另一个话筒在连接/录音/收尾中
    this.faceStartTurn(side);
  },
  onFaceMicUp(e) {
    const side = e.currentTarget.dataset.side;
    if (this.data.faceActiveSide !== side) return;
    this.faceEndTurn(side);
  },

  async faceStartTurn(side) {
    this.stopAudioPlayback();  // 停掉正在播的译文，避免串进新录音
    if (this.live) { try { this.live.close(); } catch (e) {} this.live = null; }
    if (this.recorder && this.recorder.isRecording) { try { this.recorder.stop(); } catch (e) {} }

    this.faceTurnSeq += 1;
    this.faceCurrentTurnId = 't' + this.faceTurnSeq + '_' + Date.now();
    this.faceCurSide = side;
    this.faceResetTurnText();

    const source = side === 'mine' ? this.data.faceMyLang : this.data.facePeerLang;
    const target = side === 'mine' ? this.data.facePeerLang : this.data.faceMyLang;

    this.setData({
      faceActiveSide: side,
      statusText: '连接中...', statusState: 'warn', levelPct: 0,
      faceCur: { side, src: '', tgt: '' }, faceCurActive: true
    });

    const token = (app.globalData && app.globalData.accessToken) || '';
    this.live = new LiveTranslate({
      token,
      sourceLang: source,
      targetLang: target,
      region: 'mainland',
      audioEnabled: true,
      voice: this.data.voices[this.data.voiceIndex],
      voiceCloneMode: 'off',
      onMessage: (m) => this.handleFaceMessage(m),
      onReady: () => {
        if (this.data.faceActiveSide !== side || this.data.faceFinalizing) return;  // 连接期已松手
        this.recorder.start();
        this.setData({ faceRecording: true, statusText: '聆听中', statusState: 'active' });
        if (wx.vibrateShort) wx.vibrateShort({ type: 'light' });
      },
      onError: (err) => {
        console.error('face live error', err);
        this.faceAbortTurn('出错：' + (err.message || '未知错误'));
      }
    });

    try {
      await this.live.connect();
    } catch (err) {
      console.error('face connect fail', err);
      this.faceAbortTurn('连接失败：' + (err.message || '网络错误'));
    }
  },

  faceEndTurn(side) {
    if (this.data.faceActiveSide !== side) return;
    if (this.recorder) this.recorder.stop();
    this.setData({ faceRecording: false, faceFinalizing: true, statusText: '翻译中...', statusState: 'warn', levelPct: 0 });

    const live = this.live;
    if (!live) { this.faceFinalizeTurn(); return; }

    const sent = live.finish();  // server: commit + 等 response.done → 推 session_finished

    if (this.faceFinalizingTimer) clearTimeout(this.faceFinalizingTimer);
    this.faceFinalizingTimer = setTimeout(() => {
      this.faceFinalizingTimer = null;
      this.faceFinalizeTurn();
    }, 15000);

    if (!sent) this.faceFinalizeTurn();
  },

  faceAbortTurn(msg) {
    if (this.recorder) this.recorder.stop();
    const live = this.live;
    this.live = null;
    if (live) { try { live.close(); } catch (e) {} }
    if (this.faceFinalizingTimer) { clearTimeout(this.faceFinalizingTimer); this.faceFinalizingTimer = null; }
    this.faceResetTurnText();
    this.setData({
      faceRecording: false, faceFinalizing: false, faceActiveSide: '',
      statusText: msg || '按住话筒说话', statusState: 'idle', levelPct: 0,
      faceCur: { side: '', src: '', tgt: '' }, faceCurActive: false
    });
  },

  faceFinalizeTurn() {
    if (this.faceFinalizingTimer) { clearTimeout(this.faceFinalizingTimer); this.faceFinalizingTimer = null; }
    const live = this.live;
    this.live = null;
    if (live) setTimeout(() => { try { live.close(); } catch (e) {} }, 300);

    const cur = this.data.faceCur;
    const turns = this.data.faceTurns.slice();
    if (cur && (cur.src || cur.tgt)) {
      turns.push({ id: this.faceCurrentTurnId, side: cur.side, src: cur.src, tgt: cur.tgt });
    }
    this.faceResetTurnText();
    this.setData({
      faceTurns: turns,
      faceCur: { side: '', src: '', tgt: '' }, faceCurActive: false,
      faceFinalizing: false, faceActiveSide: '',
      statusText: '按住话筒说话', statusState: 'idle'
    });
    this.faceScrollToBottom();
  },

  handleFaceMessage(m) {
    if (m.type === 'model_audio_wav') { this.enqueueAudio(m.audio); return; }
    if (m.type !== 'model_event') return;
    if (m.session_finished) { this.faceFinalizeTurn(); return; }
    if (m.status === 'translating') this.setData({ statusText: '翻译中...', statusState: 'warn' });
    if (m.status === 'listening' && this.data.faceRecording) this.setData({ statusText: '聆听中', statusState: 'active' });
    if (m.source_partial) this.faceOnPartial('src', m.source_partial);
    if (m.source_final) this.faceOnFinal('src', m.source_final);
    if (m.translation_partial) this.faceOnPartial('tgt', m.translation_partial);
    if (m.translation_final) this.faceOnFinal('tgt', m.translation_final);
  },

  faceResetTurnText() {
    this.faceCommittedSrc = ''; this.faceLiveSrc = '';
    this.faceCommittedTgt = ''; this.faceLiveTgt = '';
  },
  faceOnPartial(kind, text) {
    const next = this.normalizeText(text);
    if (!next) return;
    if (kind === 'src') this.faceLiveSrc = next; else this.faceLiveTgt = next;
    this.faceRenderCur();
  },
  faceOnFinal(kind, text) {
    const f = this.normalizeText(text);
    if (kind === 'src') {
      if (f) this.faceCommittedSrc = this.faceCommittedSrc ? this.faceCommittedSrc + ' ' + f : f;
      this.faceLiveSrc = '';
    } else {
      if (f) this.faceCommittedTgt = this.faceCommittedTgt ? this.faceCommittedTgt + ' ' + f : f;
      this.faceLiveTgt = '';
    }
    this.faceRenderCur();
  },
  faceRenderCur() {
    const src = this.faceCommittedSrc + (this.faceLiveSrc ? (this.faceCommittedSrc ? ' ' : '') + this.faceLiveSrc : '');
    const tgt = this.faceCommittedTgt + (this.faceLiveTgt ? (this.faceCommittedTgt ? ' ' : '') + this.faceLiveTgt : '');
    const tick = this.data.faceTick + 1;
    this.setData({
      faceCur: { side: this.faceCurSide, src, tgt },
      faceTick: tick,
      faceBottomView: 'fbe' + tick,
      faceTopView: 'fte' + tick
    });
  },
  faceScrollToBottom() {
    const tick = this.data.faceTick + 1;
    this.setData({ faceTick: tick, faceBottomView: 'fbe' + tick, faceTopView: 'fte' + tick });
  },

  onFaceClear() {
    this.setData({ faceTurns: [], faceCur: { side: '', src: '', tgt: '' }, faceCurActive: false });
  },
  onFaceToggleSettings() { this.setData({ faceShowSettings: true }); },
  onFaceSettingsClose() { this.setData({ faceShowSettings: false }); },
  faceNoop() {},

  // —— 拍照翻译 ——
  async onPhotoTranslate() {
    if (this.data.running) {
      wx.showToast({ title: '请先停止同传', icon: 'none' });
      return;
    }
    if (this.data.photoLoading) return;

    let chooseRes;
    try {
      chooseRes = await wx.chooseMedia({
        count: 1,
        mediaType: ['image'],
        sourceType: ['album', 'camera'],
        camera: 'back',
        sizeType: ['compressed']
      });
    } catch (e) {
      return; // 用户取消
    }
    const file = chooseRes.tempFiles && chooseRes.tempFiles[0];
    if (!file) return;

    let path = file.tempFilePath;
    try {
      const comp = await wx.compressImage({ src: path, quality: 60 });
      path = comp.tempFilePath;
    } catch (e) { /* 压缩失败则用原图 */ }

    let b64;
    try {
      b64 = await new Promise((resolve, reject) => {
        wx.getFileSystemManager().readFile({
          filePath: path,
          encoding: 'base64',
          success: (r) => resolve(r.data),
          fail: reject
        });
      });
    } catch (e) {
      wx.showToast({ title: '图片读取失败', icon: 'none' });
      return;
    }

    this.setData({ photoLoading: true, statusText: '识别中...', statusState: 'warn' });
    try {
      const res = await new Promise((resolve, reject) => {
        wx.request({
          url: PHOTO_TRANSLATE_URL,
          method: 'POST',
          timeout: 60000,
          header: { 'Content-Type': 'application/json' },
          data: {
            imageBase64: b64,
            sourceLang: this.data.sourceLangs[this.data.photoSourceIndex].code,
            targetLang: this.data.targetLangs[this.data.photoTargetIndex].code
          },
          success: resolve,
          fail: reject
        });
      });
      const r = res.data || {};
      if (r.code === 0 && r.data) {
        this.setData({
          photoSource: r.data.sourceText || '',
          photoTranslation: r.data.translation || '',
          statusText: '拍照翻译完成',
          statusState: 'idle'
        });
      } else {
        wx.showToast({ title: r.message || '识别失败', icon: 'none' });
        this.setData({ statusText: '待机', statusState: 'idle' });
      }
    } catch (e) {
      console.error('photo-translate error', e);
      wx.showToast({ title: '请求失败，请重试', icon: 'none' });
      this.setData({ statusText: '待机', statusState: 'idle' });
    } finally {
      this.setData({ photoLoading: false });
    }
  }
});
