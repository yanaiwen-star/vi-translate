const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');

function loadApp(loginResult) {
  const apiPath = path.resolve(__dirname, '../utils/api.js');
  const appPath = path.resolve(__dirname, '../app.js');
  require.cache[apiPath] = {
    exports: {
      setTokens() {},
      request: async (_method, route) => (
        route === '/api/wx/login' ? loginResult : {}
      ),
    },
  };
  global.wx = { login: async () => ({ code: 'code' }) };
  let config;
  global.App = (value) => { config = value; };
  delete require.cache[appPath];
  require(appPath);
  return { ...config, globalData: { ...config.globalData } };
}

test('clears shared login promise after success', async () => {
  const app = loadApp({ access_token: 'a', refresh_token: 'r' });
  await app.login();
  await Promise.resolve();
  assert.equal(app.globalData.loginPromise, null);
});

test('clears shared login promise after an empty login result', async () => {
  const app = loadApp({});
  await app.login();
  await Promise.resolve();
  assert.equal(app.globalData.loginPromise, null);
});

test('requests microphone permission at runtime without invalid app.json permission', () => {
  const appJson = JSON.parse(
    fs.readFileSync(path.resolve(__dirname, '../app.json'), 'utf8')
  );
  const indexSource = fs.readFileSync(
    path.resolve(__dirname, '../pages/index/index.js'),
    'utf8'
  );

  assert.equal(appJson.permission, undefined);
  assert.match(indexSource, /wx\.authorize\(\{ scope: 'scope\.record' \}\)/);
});
