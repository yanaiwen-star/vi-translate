// utils/recorder.js
// 录音管理器 - 封装 wx.getRecorderManager
// 支持 PCM 流式 + 整段两种模式

class RecorderManager {
  constructor() {
    this.recorder = null;
    this.isRecording = false;
    this.startTime = 0;
    this.chunks = [];          // 整段模式：累积 PCM 帧
    this.onProgress = null;    // 录音中回调（音量、时长）
    this.onStop = null;        // 录音结束回调
    this.onError = null;
    this.audioSource = 'auto';
  }

  /**
   * 初始化录音器
   * @param {object} options
   *   - mode: 'pcm' 流式 / 'file' 整段
   *   - duration: 最大时长（秒），0 = 不限
   */
  init(options = {}) {
    const { mode = 'pcm', duration = 30 } = options;
    this.mode = mode;
    this.maxDuration = duration * 1000;

    this.recorder = wx.getRecorderManager();

    // Prefer the operating system's communication audio path when available.
    // On supported phones this enables hardware acoustic echo cancellation.
    if (wx.getAvailableAudioSources) {
      wx.getAvailableAudioSources({
        success: (res) => {
          const sources = (res && res.audioSources) || [];
          if (sources.indexOf('voice_communication') >= 0) {
            this.audioSource = 'voice_communication';
          }
        },
        fail: () => {}
      });
    }

    this.recorder.onStart(() => {
      this.isRecording = true;
      this.startTime = Date.now();
      this.chunks = [];
      console.log('[recorder] start');
    });

    this.recorder.onStop((res) => {
      this.isRecording = false;
      const duration = Date.now() - this.startTime;
      console.log('[recorder] stop, duration:', duration, 'ms');
      if (this.onStop) {
        this.onStop({
          tempFilePath: res.tempFilePath,
          duration,
          fileSize: res.fileSize
        });
      }
    });

    this.recorder.onError((err) => {
      this.isRecording = false;
      console.error('[recorder] error', err);
      if (this.onError) this.onError(err);
    });

    // 逐帧回调：实时同传时把 PCM 帧发给翻译服务
    this.recorder.onFrameRecorded((res) => {
      const { frameBuffer } = res;
      if (this.mode === 'pcm') {
        this.chunks.push(frameBuffer);
      }
      if (this.onFrame) {
        this.onFrame(frameBuffer);
      }
      if (this.onProgress) {
        this.onProgress({
          // 估算音量（PCM 16bit 取平均值）
          volume: this.calcVolume(frameBuffer)
        });
      }
    });
  }

  // 估算音量
  calcVolume(pcmBuffer) {
    if (!pcmBuffer || pcmBuffer.byteLength < 2) return 0;
    const dataView = new DataView(pcmBuffer);
    let sum = 0;
    const len = pcmBuffer.byteLength / 2;
    for (let i = 0; i < len; i++) {
      sum += Math.abs(dataView.getInt16(i * 2, true));
    }
    return Math.min(100, Math.round((sum / len) / 32768 * 200));
  }

  start() {
    if (!this.recorder) {
      throw new Error('Recorder not initialized');
    }
    this.recorder.start({
      // RecorderManager 单次最长 10 分钟；0 在部分真机会退回短默认值。
      // 上层会在自然结束后无缝续录，直到用户主动停止。
      duration: this.maxDuration > 0 ? Math.min(this.maxDuration, 600000) : 600000,
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 48000,
      audioSource: this.audioSource,
      frameSize: 4,
      format: 'PCM'
    });
  }

  stop() {
    if (!this.recorder || !this.isRecording) return;
    this.recorder.stop();
  }

  // 拼接所有 PCM 帧为完整 ArrayBuffer
  getFullPCM() {
    if (!this.chunks.length) return null;
    const totalLen = this.chunks.reduce((acc, c) => acc + c.byteLength, 0);
    const result = new ArrayBuffer(totalLen);
    const view = new Uint8Array(result);
    let offset = 0;
    for (const chunk of this.chunks) {
      view.set(new Uint8Array(chunk), offset);
      offset += chunk.byteLength;
    }
    return result;
  }

  destroy() {
    if (this.recorder) {
      this.recorder.stop();
    }
    this.recorder = null;
    this.isRecording = false;
  }
}

// PCM ArrayBuffer 转 base64
function arrayBufferToBase64(buffer) {
  // 小程序环境有 wx.arrayBufferToBase64
  if (wx.arrayBufferToBase64) {
    return wx.arrayBufferToBase64(buffer);
  }
  // 浏览器兼容 fallback
  let binary = '';
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  // btoa 在新版基础库可用
  return typeof btoa !== 'undefined' ? btoa(binary) : binary;
}

module.exports = {
  RecorderManager,
  arrayBufferToBase64
};
