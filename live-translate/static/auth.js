/* ============================================================================
 * vi-translate 全局认证助手 (static/auth.js)
 *
 * 用法：所有需要鉴权的页面 <script src="/static/auth.js"></script> 后调用
 *   - vtFetch(url, options)  自动带 Bearer token；401 时自动 refresh 后重试
 *   - vtGet(url)             GET 快捷方式
 *   - vtPost(url, body)      POST 快捷方式，自动 JSON 序列化
 *   - vtLogout()             清掉 token 跳登录页
 *
 * 事件：refresh 失败时派发 `vt:auth-expired`，页面可监听后跳登录页或弹提示。
 *
 * Token 有效期（来自 .env / config.py）：
 *   - access_token: 60 分钟（默认）
 *   - refresh_token: 30 天
 * 用户在不刷新页面的情况下连续使用本工具，60 分钟后会自动 refresh，
 * 体感上等同「保持登录状态」。刷新页面也会从 localStorage 拿到新 token。
 * ============================================================================ */
(function () {
  'use strict';

  const TOKEN_KEY = 'vt_token';
  const REFRESH_KEY = 'vt_refresh';

  // 防止多个并发 401 触发多次 refresh 请求：所有调用共享同一个 Promise。
  let refreshingPromise = null;

  function getToken() { return localStorage.getItem(TOKEN_KEY) || ''; }
  function getRefresh() { return localStorage.getItem(REFRESH_KEY) || ''; }
  function setTokens(accessToken, refreshToken) {
    if (accessToken) localStorage.setItem(TOKEN_KEY, accessToken);
    if (refreshToken) localStorage.setItem(REFRESH_KEY, refreshToken);
  }
  function clearTokens() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
  }

  async function refreshAccessToken() {
    if (refreshingPromise) return refreshingPromise;
    const rt = getRefresh();
    if (!rt) throw new Error('no refresh token');

    refreshingPromise = (async () => {
      try {
        const r = await fetch('/auth/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: rt }),
        });
        if (!r.ok) {
          // refresh token 也过期了（或无效），清掉让用户重登
          clearTokens();
          throw new Error('refresh failed: HTTP ' + r.status);
        }
        const d = await r.json();
        setTokens(d.access_token, d.refresh_token);
        return d.access_token;
      } finally {
        refreshingPromise = null;
      }
    })();

    return refreshingPromise;
  }

  /**
   * 包装 fetch：自动加 Bearer token，401 时自动 refresh + 重试一次。
   * 重试仍 401 则清 token 并派发 'vt:auth-expired' 事件，由页面自行跳转登录页。
   *
   * 注意：只在 body 不是 FormData / Blob / ArrayBuffer 时才自动加 Content-Type。
   *       401 只对 /auth/me /billing/* 等需要鉴权的接口敏感；登录接口自己处理。
   */
  async function vtFetch(url, options) {
    options = options || {};
    const headers = new Headers(options.headers || {});
    if (!headers.has('Authorization') && getToken()) {
      headers.set('Authorization', 'Bearer ' + getToken());
    }
    // 自动 JSON Content-Type（如果不是上传类请求且 caller 没显式设置）
    if (
      options.body &&
      typeof options.body === 'string' &&
      !headers.has('Content-Type')
    ) {
      headers.set('Content-Type', 'application/json');
    }
    options.headers = headers;

    let r = await fetch(url, options);
    if (r.status !== 401) return r;

    // 401：尝试 refresh 后重试一次
    if (!getRefresh()) {
      clearTokens();
      window.dispatchEvent(new CustomEvent('vt:auth-expired'));
      return r;
    }
    try {
      const newToken = await refreshAccessToken();
      headers.set('Authorization', 'Bearer ' + newToken);
      r = await fetch(url, options);
      if (r.status === 401) {
        clearTokens();
        window.dispatchEvent(new CustomEvent('vt:auth-expired'));
      }
      return r;
    } catch (e) {
      console.warn('[vt-auth] refresh failed:', e);
      clearTokens();
      window.dispatchEvent(new CustomEvent('vt:auth-expired'));
      return r;
    }
  }

  const vtGet = function (url) {
    return vtFetch(url, { method: 'GET' });
  };
  const vtPost = function (url, body) {
    return vtFetch(url, {
      method: 'POST',
      body: body != null ? JSON.stringify(body) : undefined,
    });
  };
  const vtPut = function (url, body) {
    return vtFetch(url, {
      method: 'PUT',
      body: body != null ? JSON.stringify(body) : undefined,
    });
  };

  function vtLogout() {
    clearTokens();
    location.href = '/login.html';
  }

  // 暴露给页面用
  window.vtAuth = {
    getToken, getRefresh, setTokens, clearTokens,
    fetch: vtFetch,
    get: vtGet,
    post: vtPost,
    put: vtPut,
    logout: vtLogout,
    refresh: refreshAccessToken,
  };
})();