// pages/face/face.js
// 面对面翻译 —— 双话筒·一人一句（PTT 按住说话）
// 上话筒 = 对方（peer），下话筒 = 我（mine）；各话筒自带语言方向，松开发 finish 收这句。
// 复用首页同传后端 /ws/livetranslate（utils/live.js）。
// 关键设计：全程只用一根 this.live，同一时刻只允许一个话筒录音 → 录音帧永远发对地方。

const { RecorderManager } = require('../../utils/recorder.js');
const { LiveTranslate } = require('../../utils/live.js');

const app = getApp();

const LANGS = [
  { code: 'zh', label: '中文' },
  { code: 'vi', label: '越南语' },
  { code: 'en', label: '英语' },
  { code: 'ja', label: '日语' },
  { code: 'ko', label: '韩语' }
];

Page({
  data: {
    langOptions: LANGS,
    myLangIndex: 0,
    myLang: 'zh',
    myLangLabel: '中文',
    peerLangIndex: 1,
    peerLang: 'vi',
    peerLangLabel: '越南语',

    statusText: '按住话筒说话',
    statusClass: 'idle',
    levelPct: 0,
    showSettings: false,

    activeSide: '',      // '' | 'mine' | 'peer'（当前占用话筒的一方）
    recording: false,
    finalizing: false,

    turns: [],           // 已完成回合 [{id, side, src, tgt}]
    cur: { side: '', src: '', tgt: '' },  // 正在录的回合（草稿实时刷新）
    curActive: false,

    // 自动滚动到底（tick 变化触发 scroll-into-view 重新定位）
    tick: 0,
    bottomView: '',
    topView: ''
  },

  recorder: null,
  live: null,
  turnSeq: 0,
  currentTurnId: '',
  curSide: '',
  finalizingTimer: null,

  // 文本累积：一句回合内可能有多个 final（断句），partial 是进行中的快照
  committedSrc: '',
  liveSrc: '',
  committedTgt: '',
  liveTgt: '',

  ttsPlaying: false,
  ttsTailTimer: null,
  audioQueue: [],
  playingAudio: null,

  onLoad() {
    const my = wx.getStorageSync('face_my_lang') || 'zh';
    const peer = wx.getStorageSync('face_peer_lang') || 'vi';
    this.applyLangs(my, peer);

    this.recorder = new RecorderManager();
    this.recorder.init({ mode: 'pcm', duration: 0 });
    this.recorder.onProgress = (info) => {
      if (this.ttsPlaying) return;
      this.setData({ levelPct: Math.min(100, info.volume || 0) });
    };
    this.recorder.onFrame = (frame) => {
      if (this.ttsPlaying) return;   // 播放译文时屏蔽麦克风上送，破回声
      if (this.live && this.live.connected) this.live.sendAudioFrame(frame);
    };
    this.recorder.onError = (err) => {
      console.error('recorder error', err);
      this.abortTurn('录音失败，请重试');
    };
  },

  onUnload() { this.destroySession(); },
  onHide() { if (this.data.activeSide) this.endTurn(this.data.activeSide); },

  applyLangs(myCode, peerCode) {
    const myIdx = Math.max(0, LANGS.findIndex((l) => l.code === myCode));
    const peerIdx = Math.max(0, LANGS.findIndex((l) => l.code === peerCode));
    this.setData({
      myLangIndex: myIdx,
      myLang: LANGS[myIdx].code,
      myLangLabel: LANGS[myIdx].label,
      peerLangIndex: peerIdx,
      peerLang: LANGS[peerIdx].code,
      peerLangLabel: LANGS[peerIdx].label
    });
  },

  // ===== 中间语种切换 =====
  onSwapLangs() {
    const newMy = this.data.peerLang;
    const newPeer = this.data.myLang;
    this.applyLangs(newMy, newPeer);
    wx.setStorageSync('face_my_lang', newMy);
    wx.setStorageSync('face_peer_lang', newPeer);
  },
  onChangeMyLang(e) {
    const idx = Number(e.detail.value);
    this.applyLangs(LANGS[idx].code, this.data.peerLang);
    wx.setStorageSync('face_my_lang', LANGS[idx].code);
  },
  onChangePeerLang(e) {
    const idx = Number(e.detail.value);
    this.applyLangs(this.data.myLang, LANGS[idx].code);
    wx.setStorageSync('face_peer_lang', LANGS[idx].code);
  },

  // ===== 话筒 PTT =====
  onMicDown(e) {
    const side = e.currentTarget.dataset.side;
    if (this.data.activeSide) return;  // 互斥：另一个话筒在连接/录音/收尾中
    this.startTurn(side);
  },
  onMicUp(e) {
    const side = e.currentTarget.dataset.side;
    if (this.data.activeSide !== side) return;
    this.endTurn(side);
  },

  async startTurn(side) {
    // 停掉正在播放的译文，避免它串进新的录音
    this.stopAudioPlayback();
    if (this.live) { try { this.live.close(); } catch (e) {} this.live = null; }
    if (this.recorder && this.recorder.isRecording) { try { this.recorder.stop(); } catch (e) {} }

    this.turnSeq += 1;
    this.currentTurnId = 't' + this.turnSeq + '_' + Date.now();
    this.curSide = side;
    this.resetTurnText();

    const source = side === 'mine' ? this.data.myLang : this.data.peerLang;
    const target = side === 'mine' ? this.data.peerLang : this.data.myLang;

    this.setData({
      activeSide: side,
      statusText: '连接中…', statusClass: 'warn', levelPct: 0,
      cur: { side, src: '', tgt: '' }, curActive: true
    });

    const token = (app.globalData && app.globalData.accessToken) || '';
    this.live = new LiveTranslate({
      token,
      providerMode: wx.getStorageSync('qwen_provider_mode') === 'byok' ? 'byok' : 'platform',
      sourceLang: source,
      targetLang: target,
      region: 'mainland',
      audioEnabled: true,
      voice: 'Tina',
      voiceCloneMode: 'off',
      onMessage: (m) => this.handleMessage(m),
      onReady: () => {
        // 连接期间用户可能已松手（finalizing）或已切换 → 不再启动录音
        if (this.data.activeSide !== side || this.data.finalizing) return;
        this.recorder.start();
        this.setData({ recording: true, statusText: '聆听中', statusClass: 'active' });
        if (wx.vibrateShort) wx.vibrateShort({ type: 'light' });
      },
      onError: (err) => {
        console.error('live error', err);
        this.abortTurn('出错：' + (err.message || '未知错误'));
      }
    });

    try {
      await this.live.connect();
    } catch (err) {
      console.error('connect fail', err);
      this.abortTurn('连接失败：' + (err.message || '网络错误'));
    }
  },

  endTurn(side) {
    if (this.data.activeSide !== side) return;
    if (this.recorder) this.recorder.stop();
    this.setData({ recording: false, finalizing: true, statusText: '翻译中…', statusClass: 'warn', levelPct: 0 });

    const live = this.live;
    if (!live) { this.finalizeTurn(); return; }

    // 优雅结束：通知 server「我说完了，把剩余翻译推完再推 session_finished」。
    // server 收到后 input_audio_buffer.commit + 等 response.done（已部署），最多 5s。
    const sent = live.finish();

    // 15s 兜底：没收到 session_finished 也强制收尾，防卡死
    if (this.finalizingTimer) clearTimeout(this.finalizingTimer);
    this.finalizingTimer = setTimeout(() => {
      this.finalizingTimer = null;
      this.finalizeTurn();
    }, 15000);

    if (!sent) {
      // finish 没发出去（ws 已断）→ 直接收尾
      this.finalizeTurn();
    }
  },

  abortTurn(msg) {
    if (this.recorder) this.recorder.stop();
    const live = this.live;
    this.live = null;
    if (live) { try { live.close(); } catch (e) {} }
    if (this.finalizingTimer) { clearTimeout(this.finalizingTimer); this.finalizingTimer = null; }
    this.resetTurnText();
    this.setData({
      recording: false, finalizing: false, activeSide: '',
      statusText: msg || '已停止', statusClass: 'idle', levelPct: 0,
      cur: { side: '', src: '', tgt: '' }, curActive: false
    });
  },

  finalizeTurn() {
    if (this.finalizingTimer) { clearTimeout(this.finalizingTimer); this.finalizingTimer = null; }
    const live = this.live;
    this.live = null;
    if (live) setTimeout(() => { try { live.close(); } catch (e) {} }, 300);

    // 把当前回合并入 turns（有内容才并）
    const cur = this.data.cur;
    const turns = this.data.turns.slice();
    if (cur && (cur.src || cur.tgt)) {
      turns.push({ id: this.currentTurnId, side: cur.side, src: cur.src, tgt: cur.tgt });
    }
    this.resetTurnText();
    this.setData({
      turns,
      cur: { side: '', src: '', tgt: '' }, curActive: false,
      finalizing: false, activeSide: '',
      statusText: '按住话筒说话', statusClass: 'idle'
    });
    this.scrollToBottom();
  },

  destroySession() {
    if (this.live) { try { this.live.close(); } catch (e) {} this.live = null; }
    if (this.recorder) this.recorder.destroy();
    if (this.playingAudio) { try { this.playingAudio.destroy(); } catch (e) {} this.playingAudio = null; }
    if (this.ttsTailTimer) { clearTimeout(this.ttsTailTimer); this.ttsTailTimer = null; }
    if (this.finalizingTimer) { clearTimeout(this.finalizingTimer); this.finalizingTimer = null; }
    this.ttsPlaying = false;
    this.audioQueue = [];
  },

  // ===== 服务器消息 =====
  handleMessage(m) {
    if (m.type === 'model_audio_wav') { this.enqueueAudio(m.audio); return; }
    if (m.type !== 'model_event') return;

    if (m.session_finished) { this.finalizeTurn(); return; }
    if (m.status === 'translating') this.setData({ statusText: '翻译中…', statusClass: 'warn' });
    if (m.status === 'listening' && this.data.recording) this.setData({ statusText: '聆听中', statusClass: 'active' });

    if (m.source_partial) this.onPartial('src', m.source_partial);
    if (m.source_final) this.onFinal('src', m.source_final);
    if (m.translation_partial) this.onPartial('tgt', m.translation_partial);
    if (m.translation_final) this.onFinal('tgt', m.translation_final);
  },

  norm(t) { return String(t || '').replace(/\s+/g, ' ').trim(); },

  resetTurnText() {
    this.committedSrc = ''; this.liveSrc = '';
    this.committedTgt = ''; this.liveTgt = '';
  },

  onPartial(kind, text) {
    const next = this.norm(text);
    if (!next) return;
    if (kind === 'src') this.liveSrc = next; else this.liveTgt = next;
    this.renderCur();
  },
  onFinal(kind, text) {
    const f = this.norm(text);
    if (kind === 'src') {
      if (f) this.committedSrc = this.committedSrc ? this.committedSrc + ' ' + f : f;
      this.liveSrc = '';
    } else {
      if (f) this.committedTgt = this.committedTgt ? this.committedTgt + ' ' + f : f;
      this.liveTgt = '';
    }
    this.renderCur();
  },

  renderCur() {
    const src = this.committedSrc + (this.liveSrc ? (this.committedSrc ? ' ' : '') + this.liveSrc : '');
    const tgt = this.committedTgt + (this.liveTgt ? (this.committedTgt ? ' ' : '') + this.liveTgt : '');
    const tick = this.data.tick + 1;
    this.setData({
      cur: { side: this.curSide, src, tgt },
      tick,
      bottomView: 'be' + tick,
      topView: 'te' + tick
    });
  },

  scrollToBottom() {
    const tick = this.data.tick + 1;
    this.setData({ tick, bottomView: 'be' + tick, topView: 'te' + tick });
  },

  onClear() {
    this.setData({ turns: [], cur: { side: '', src: '', tgt: '' }, curActive: false });
  },

  // ===== 译文 TTS 播放 =====
  enqueueAudio(b64) {
    if (!b64) return;
    const fs = wx.getFileSystemManager();
    const path = `${wx.env.USER_DATA_PATH}/face_tts_${Date.now()}_${Math.floor(Math.random() * 1e4)}.wav`;
    fs.writeFile({
      filePath: path,
      data: wx.base64ToArrayBuffer(b64),
      success: () => { this.audioQueue.push(path); this.playNextAudio(); },
      fail: () => {}
    });
  },
  playNextAudio() {
    if (this.playingAudio || !this.audioQueue.length) return;
    const path = this.audioQueue.shift();
    const a = wx.createInnerAudioContext();
    this.playingAudio = a;
    this.ttsPlaying = true;
    if (this.ttsTailTimer) { clearTimeout(this.ttsTailTimer); this.ttsTailTimer = null; }
    this.setData({ levelPct: 0 });
    a.src = path;
    a.obeyMuteSwitch = false;
    const onDone = () => {
      try { a.destroy(); } catch (e) {}
      try { wx.getFileSystemManager().unlink({ filePath: path }); } catch (e) {}
      this.playingAudio = null;
      if (this.audioQueue.length) {
        this.playNextAudio();
      } else if (!this.data.recording) {
        this.ttsPlaying = false;
      } else {
        if (this.ttsTailTimer) clearTimeout(this.ttsTailTimer);
        this.ttsTailTimer = setTimeout(() => { this.ttsPlaying = false; this.ttsTailTimer = null; }, 350);
      }
    };
    a.onEnded(onDone);
    a.onError(onDone);
    a.play();
  },
  stopAudioPlayback() {
    if (this.playingAudio) {
      try { this.playingAudio.stop(); } catch (e) {}
      try { this.playingAudio.destroy(); } catch (e) {}
      this.playingAudio = null;
    }
    if (this.ttsTailTimer) { clearTimeout(this.ttsTailTimer); this.ttsTailTimer = null; }
    this.audioQueue = [];
    this.ttsPlaying = false;
  },

  // ===== 设置 =====
  onToggleSettings() { this.setData({ showSettings: true }); },
  onSettingsClose() { this.setData({ showSettings: false }); },
  noop() {},

  onShareAppMessage() {
    return { title: '面对面翻译·和身边的人一起聊', path: '/pages/face/face' };
  }
});
