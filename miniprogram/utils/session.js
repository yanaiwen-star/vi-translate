// utils/session.js
// 会话管理 - 对接 ECS 后端 /api/sessions（与官网后台共用同一数据库）

const app = getApp();
const { request } = require('./api.js');

function formatTime(date) {
  const pad = n => String(n).padStart(2, '0');
  return `${date.getMonth() + 1}/${date.getDate()} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/**
 * 创建或获取当前会话（优先服务端；登录未完成时临时用本地 id 但不长期缓存，
 * 下次调用会重试服务端，确保历史最终落到服务器）。
 */
async function ensureSession() {
  const cached = app.globalData.currentSessionId;
  if (cached && !cached.startsWith('local_')) {
    return cached;
  }

  // 等 app.login() 完成，避免 onLaunch 异步登录未到位时第一次 POST /api/sessions 401。
  // 登录成功后 storage 里有 access_token，再发起请求才能拿到 200。
  await app.login();
  // 登录后再次检查缓存：可能别的并发 ensureSession 已写入 sessionId
  const cached2 = app.globalData.currentSessionId;
  if (cached2 && !cached2.startsWith('local_')) {
    return cached2;
  }

  try {
    const res = await request('POST', '/api/sessions', {
      title: `会话 ${formatTime(new Date())}`
    });
    if (res && res.sessionId) {
      app.globalData.currentSessionId = res.sessionId;
      return res.sessionId;
    }
    throw new Error('no sessionId');
  } catch (err) {
    console.error('创建会话失败（将使用临时本地 id，登录完成后重试）', err);
    // 降级：临时本地 id，不写入 globalData，下次仍会重试服务端
    return 'local_' + Date.now();
  }
}

/**
 * 保存一条消息
 */
async function saveMessage(message) {
  try {
    const res = await request('POST', `/api/sessions/${message.sessionId}/messages`, {
      sourceLang: message.sourceLang,
      sourceText: message.sourceText,
      targetLang: message.targetLang,
      targetText: message.targetText,
      audioDuration: message.audioDuration || 0
    });
    return res;
  } catch (err) {
    console.error('保存消息失败', err);
    return null;
  }
}

/**
 * 获取历史会话列表
 */
async function listSessions(limit = 50) {
  try {
    const res = await request('GET', `/api/sessions?limit=${limit}`);
    const list = (res && res.list) || [];
    return list.map(s => ({
      _id: s.id,
      title: s.title,
      previewText: s.previewText,
      messageCount: s.messageCount || 0,
      updatedAtText: formatTime(new Date(s.updatedAt))
    }));
  } catch (err) {
    console.error('获取会话列表失败', err);
    return [];
  }
}

/**
 * 获取某会话的消息
 */
async function getMessages(sessionId) {
  try {
    const res = await request('GET', `/api/sessions/${sessionId}`);
    const list = (res && res.list) || [];
    return list.map(m => ({
      _id: m.id,
      sourceLang: m.sourceLang,
      targetLang: m.targetLang,
      sourceText: m.sourceText,
      targetText: m.targetText,
      createdAtText: formatTime(new Date(m.createdAt))
    }));
  } catch (err) {
    console.error('获取消息失败', err);
    return [];
  }
}

/**
 * 删除会话
 */
async function deleteSession(sessionId) {
  try {
    return await request('DELETE', `/api/sessions/${sessionId}`);
  } catch (err) {
    console.error('删除会话失败', err);
    return null;
  }
}

module.exports = {
  ensureSession,
  saveMessage,
  listSessions,
  getMessages,
  deleteSession
};
