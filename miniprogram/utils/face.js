// utils/face.js
// 面对面翻译 WebSocket 客户端 —— 连接 yuexunfanyi.com/ws/face
// 服务端：app/face/proxy.py（房间配对 + 双向转发 DashScope 实时翻译）
//
// 协议：
//   1) connect：把 room / my_lang / nickname / token 放进 query 连接
//      wss://yuexunfanyi.com/ws/face?room=XXX&my_lang=zh|vi&nickname=..&token=..
//   2) 发送：二进制 PCM 帧（isBuffer:true）+ JSON 控制消息 {type:'mic_on'|'mic_off'}
//   3) 接收：joined / waiting_for_peer / peer_joined / peer_left /
//            server_ready / server_error / socket_close /
//            model_event（含 translation_partial/final、status）/
//            model_audio_wav（base64 WAV）
//      所有消息统一通过 onEvent(msg) 透传给页面，由页面决定如何渲染。

function generateRoomId() {
  // 去掉易混字符（0/O、1/I、8/B 等）的 6 位房间号
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let s = '';
  for (let i = 0; i < 6; i++) {
    s += chars[Math.floor(Math.random() * chars.length)];
  }
  return s;
}

const WS_BASE = 'wss://yuexunfanyi.com/ws/face';

class FaceTranslate {
  /**
   * @param {object} opts
   *   token:   登录 JWT（匿名可留空）
   *   room:    房间号（大小写不敏感，内部转大写）
   *   myLang:  'zh' | 'vi'（自己说的语种）
   *   nickname: 展示给对方用的昵称
   *   region:  'mainland' | 'intl'
   *   onEvent(msg): 收到任意服务器消息
   *   onError(err): 连接/协议错误
   *   onClose(info): 连接关闭（info.intentional 表示主动关闭）
   */
  constructor(opts = {}) {
    this.token = opts.token || '';
    this.room = (opts.room || '').trim().toUpperCase();
    this.myLang = opts.myLang || 'zh';
    this.nickname = opts.nickname || '';
    this.region = opts.region || 'mainland';
    this.onEvent = opts.onEvent || function () {};
    this.onError = opts.onError || function () {};
    this.onCloseCb = opts.onClose || function () {};
    this.task = null;
    this.connected = false;
    this._settled = false;
    this._timer = null;
    this._closedByUs = false;
  }

  connect() {
    return new Promise((resolve, reject) => {
      const params = [];
      params.push('room=' + encodeURIComponent(this.room));
      params.push('my_lang=' + encodeURIComponent(this.myLang));
      if (this.nickname) params.push('nickname=' + encodeURIComponent(this.nickname));
      if (this.token) params.push('token=' + encodeURIComponent(this.token));
      const url = WS_BASE + '?' + params.join('&');

      const task = wx.connectSocket({ url });
      this.task = task;

      task.onOpen(() => {
        // room / my_lang 已在 query 中，服务器会自动下发 joined / waiting_for_peer
        this.connected = true;
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

        if (msg.type === 'joined' || msg.type === 'waiting_for_peer') {
          if (!this._settled) {
            this._settled = true;
            resolve(msg);
          }
        } else if (msg.type === 'server_ready') {
          this.connected = true;
        } else if (msg.type === 'server_error') {
          const err = new Error(msg.message || '服务器错误');
          if (!this._settled) {
            this._settled = true;
            reject(err);
          } else {
            this.onError(err);
          }
        } else if (msg.type === 'config_error') {
          const err = new Error(msg.message || '配置错误');
          if (!this._settled) {
            this._settled = true;
            reject(err);
          } else {
            this.onError(err);
          }
        } else if (msg.type === 'quota_exhausted') {
          this.onError(new Error(msg.message || '额度已用尽'));
        }

        // 所有消息统一透传给页面
        this.onEvent(msg);
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
        this.onCloseCb({ intentional: this._closedByUs });
      });

      this._timer = setTimeout(() => {
        if (!this._settled) {
          this._settled = true;
          reject(new Error('连接超时，请检查网络或合法域名配置'));
        }
      }, 10000);
    });
  }

  // 通知服务器开始把麦克风音频送入上游翻译（仅 mic_on 后才建立上游会话）
  micOn() {
    if (this.task && this.connected) {
      this.task.send({ data: JSON.stringify({ type: 'mic_on' }) });
    }
  }

  micOff() {
    if (this.task && this.connected) {
      this.task.send({ data: JSON.stringify({ type: 'mic_off' }) });
    }
  }

  // 发送录音 PCM 帧（ArrayBuffer）
  sendAudioFrame(arrayBuffer) {
    if (this.task && this.connected) {
      this.task.send({ data: arrayBuffer, isBuffer: true });
    }
  }

  close() {
    if (this._timer) {
      clearTimeout(this._timer);
      this._timer = null;
    }
    this._closedByUs = true;
    if (this.task) {
      try {
        this.task.close({});
      } catch (e) {}
      this.task = null;
    }
    this.connected = false;
  }
}

module.exports = { FaceTranslate, generateRoomId, WS_BASE };
