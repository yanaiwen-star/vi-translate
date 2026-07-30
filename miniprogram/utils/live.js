// utils/live.js
// 实时同传 WebSocket 客户端 —— 复用网页版 Qwen 系统（底层 DashScope realtime）
// 连接 yuexunfanyi.com/ws/livetranslate：发音频帧，收原文/译文文本 + 译文语音(WAV)
// 协议与网页版 static/app.js 完全一致（服务器做 normalize_event，字段为
// source_partial/source_final/translation_partial/translation_final/status ...）

const WS_URL = 'wss://yuexunfanyi.com/ws/livetranslate';

class LiveTranslate {
  /**
   * @param {object} opts
   *   token: 登录 JWT（匿名可留空）
   *   sourceLang / targetLang: 'auto' | 'zh' | 'vi' ...
   *   region: 'mainland' | 'intl'
   *   audioEnabled: 是否返回译文语音
   *   voice: 发音人
   *   voiceCloneMode: 'off' | 'once' | 'always'
   *   inputMode: 输入模式（保留字段，当前仅 'mic'）
   *   visualContext: 视觉上下文（保留字段，当前未使用）
   *   onMessage(event): 收到 model_event / model_audio_wav
   *   onReady(): server_ready
   *   onError(err)
   *   onClose()
   */
  constructor(opts = {}) {
    this.token = opts.token || '';
    this.sourceLang = opts.sourceLang || 'auto';
    this.targetLang = opts.targetLang || 'vi';
    this.region = opts.region || 'mainland';
    this.audioEnabled = opts.audioEnabled !== false;
    this.voice = opts.voice || 'Tina';
    this.voiceCloneMode = opts.voiceCloneMode || 'off';
    this.inputMode = opts.inputMode || 'mic';
    this.visualContext = opts.visualContext === true;
    this.onMessage = opts.onMessage || function () {};
    this.onReady = opts.onReady || function () {};
    this.onError = opts.onError || function () {};
    this.onClose = opts.onClose || function () {};
    this.task = null;
    this.connected = false;
    this._settled = false;
    this._timer = null;
  }

  connect() {
    return new Promise((resolve, reject) => {
      const url = WS_URL + (this.token ? '?token=' + encodeURIComponent(this.token) : '');
      const task = wx.connectSocket({ url });
      this.task = task;

      task.onOpen(() => {
        task.send({
          data: JSON.stringify({
            type: 'config',
            token: this.token,
            region: this.region,
            source_language: this.sourceLang,
            target_language: this.targetLang,
            audio_enabled: this.audioEnabled,
            voice: this.voice,
            voice_clone_mode: this.voiceCloneMode,
            input_mode: this.inputMode,
            visual_context: this.inputMode === 'camera' ? this.visualContext : false,
            source_config_enabled: true,
            minimal_session: false,
            voice_config_enabled: true,
            voice_clone_config_enabled: true
          })
        });
      });

      task.onMessage((res) => {
        let raw = res.data;
        if (typeof raw !== 'string') return; // 文本协议，忽略非字符串
        let msg;
        try {
          msg = JSON.parse(raw);
        } catch (e) {
          return;
        }
        if (msg.type === 'model_audio_wav') {
          console.log('[live] model_audio_wav, base64 length=', (msg.audio||'').length, 'sample_rate=', msg.sample_rate);
        } else if (msg.type === 'model_event') {
          const ev = msg;
          const flags = [];
          if (ev.source_partial) flags.push('source_partial');
          if (ev.source_final) flags.push('source_final');
          if (ev.translation_partial) flags.push('translation_partial');
          if (ev.translation_final) flags.push('translation_final');
          if (ev.status) flags.push('status=' + ev.status);
          if (ev.type) flags.push('event_type=' + ev.type);
          if (flags.length) console.log('[live] model_event:', flags.join(','));
        } else {
          console.log('[live] msg type=', msg.type, msg.message ? ('msg=' + msg.message) : '');
        }

        if (msg.type === 'server_ready') {
          this.connected = true;
          this.onReady(msg);
          if (!this._settled) {
            this._settled = true;
            resolve(msg);
          }
          return;
        }
        if (msg.type === 'server_error') {
          const err = new Error(msg.message || '服务器错误');
          // 携带后端错误码（用于前端做精细处理，如 NICKNAME_REQUIRED → 跳设置昵称页）
          if (msg.code) err.code = msg.code;
          if (!this._settled) {
            this._settled = true;
            reject(err);
          } else {
            this.onError(err);
          }
          return;
        }
        if (msg.type === 'config_error') {
          const err = new Error(msg.message || '配置错误');
          if (!this._settled) {
            this._settled = true;
            reject(err);
          } else {
            this.onError(err);
          }
          return;
        }
        if (msg.type === 'quota_exhausted') {
          this.onError(new Error(msg.message || '额度已用尽'));
          return;
        }
        // model_event / model_audio_wav
        this.onMessage(msg);
      });

      task.onError((err) => {
        if (!this._settled) {
          this._settled = true;
          reject(err);
        } else {
          this.onError(err);
        }
      });

      task.onClose(() => {
        this.connected = false;
        this.onClose();
      });

      this._timer = setTimeout(() => {
        if (!this._settled) {
          this._settled = true;
          reject(new Error('连接超时，请检查网络或合法域名配置'));
        }
      }, 10000);
    });
  }

  // 发送录音 PCM 帧（ArrayBuffer）
  sendAudioFrame(arrayBuffer) {
    if (this.task && this.connected) {
      this.task.send({ data: arrayBuffer, isBuffer: true });
    }
  }

  stop() {
    if (this.task && this.connected) {
      this.task.send({ data: 'stop' });
    }
  }

  // 请求"优雅结束"：告诉 server "我说完了，把剩余翻译推完再推 session_finished"。
  // 注意：**不关闭 socket**——server 推 session_finished 事件后才由调用方 close()。
  // 用于面对面模式的 PTT：用户 mic up 时调 finish()，等 server 把当前未完成的翻译
  // 推完后再关 ws，避免 mic up 截断了正在生成的译文。返回 true 表示已发出 finish；
  // 返回 false 表示 ws 已断或 socket.send 失败，调用方应直接 close 兜底。
  finish() {
    if (!this.task || !this.connected) return false;
    try {
      this.task.send({ data: JSON.stringify({ type: 'finish' }) });
      return true;
    } catch (e) {
      return false;
    }
  }

  close() {
    if (this._timer) {
      clearTimeout(this._timer);
      this._timer = null;
    }
    if (this.task) {
      try {
        this.task.close({});
      } catch (e) {}
      this.task = null;
    }
    this.connected = false;
  }
}

module.exports = { LiveTranslate, WS_URL };
