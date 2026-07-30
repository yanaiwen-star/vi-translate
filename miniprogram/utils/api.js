// utils/api.js — 统一请求封装，对接 ECS 后端 yuexunfanyi.com
// 后端接口：/api/wx/login（登录）、/api/wx/me（资料）、/api/wx/phone（绑定手机）
//          /auth/refresh（刷新 token）、/auth/sms/send、/auth/sms/bind（网页短信绑定）
//          /api/content、/api/sessions
//          注：小程序按微信流程获取手机号，网页用阿里云短信验证码确认。
const BASE = 'https://yuexunfanyi.com';

let _refreshing = null; // 并发时共享同一个刷新请求

function getToken() {
  try { return wx.getStorageSync('access_token') || ''; } catch (e) { return ''; }
}
function getRefresh() {
  try { return wx.getStorageSync('refresh_token') || ''; } catch (e) { return ''; }
}
function setTokens(access, refresh) {
  try {
    if (access) wx.setStorageSync('access_token', access);
    if (refresh) wx.setStorageSync('refresh_token', refresh);
  } catch (e) {}
}
function clearTokens() {
  try {
    wx.removeStorageSync('access_token');
    wx.removeStorageSync('refresh_token');
  } catch (e) {}
}

// 用 refresh_token 换新的 access_token（复用 /auth/refresh）
function doRefresh() {
  if (_refreshing) return _refreshing;
  const rt = getRefresh();
  if (!rt) return Promise.reject(new Error('no_refresh'));
  const refreshRequest = new Promise((resolve, reject) => {
    wx.request({
      url: BASE + '/auth/refresh',
      method: 'POST',
      data: { refresh_token: rt },
      success: (res) => {
        if (res.statusCode === 200 && res.data && res.data.access_token) {
          setTokens(res.data.access_token, res.data.refresh_token || rt);
          resolve(res.data.access_token);
        } else {
          reject(new Error('refresh_failed'));
        }
      },
      fail: (err) => reject(err),
    });
  });
  // 返回 finally 链本身，避免被忽略的 rejected Promise 触发 unhandledRejection。
  _refreshing = refreshRequest.finally(() => { _refreshing = null; });
  return _refreshing;
}

/**
 * @param {'GET'|'POST'|'PUT'|'DELETE'} method
 * @param {string} path  例如 '/api/content'
 * @param {*} data
 * @param {boolean} auth 是否自动带 Bearer token（登录接口传 false）
 * @param {boolean} _retried 内部递归标记，避免刷新后无限重试
 */
function request(method, path, data, auth = true, _retried = false) {
  return new Promise((resolve, reject) => {
    const header = { 'Content-Type': 'application/json' };
    if (auth) {
      const t = getToken();
      if (t) header.Authorization = 'Bearer ' + t;
    }
    wx.request({
      url: BASE + path,
      method,
      data,
      header,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else if (res.statusCode === 401 && auth && !_retried) {
          // access_token 过期：尝试用 refresh_token 刷新后重试一次
          doRefresh().then(() => {
            request(method, path, data, auth, true).then(resolve).catch(reject);
          }).catch(() => {
            clearTokens();
            reject(new Error('登录已过期，请重新登录'));
          });
        } else {
          const detail = res.data && (res.data.detail || res.data.message);
          reject(new Error(detail || ('请求失败 ' + res.statusCode)));
        }
      },
      fail: (err) => reject(err),
    });
  });
}

module.exports = { BASE, getToken, getRefresh, setTokens, clearTokens, request, doRefresh };
