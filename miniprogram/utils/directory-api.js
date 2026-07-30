const { request } = require('./api.js');
const { buildDirectoryQuery } = require('./directory.js');

function listOptions() {
  return request('GET', '/api/directory/options', {}, false);
}

function listProfiles(filters) {
  return request('GET', '/api/directory/profiles', buildDirectoryQuery(filters || {}), false);
}

function getProfile(id) { return request('GET', '/api/directory/profiles/' + encodeURIComponent(id), {}, false); }
function getMyProfile() { return request('GET', '/api/directory/me/profile', {}, true); }
function createProfile(payload) { return request('POST', '/api/directory/me/profile', payload, true); }
function updateProfile(payload) { return request('PUT', '/api/directory/me/profile', payload, true); }
function pauseProfile() { return request('POST', '/api/directory/me/profile/pause', {}, true); }
function resumeProfile() { return request('POST', '/api/directory/me/profile/resume', {}, true); }
function deleteProfile() { return request('DELETE', '/api/directory/me/profile', {}, true); }
function requestContact(profileId, purpose) { return request('POST', '/api/directory/profiles/' + encodeURIComponent(profileId) + '/contact-requests', { purpose }, true); }
function listContactRequests() { return request('GET', '/api/directory/me/contact-requests', {}, true); }
function approveContact(id) { return request('POST', '/api/directory/me/contact-requests/' + encodeURIComponent(id) + '/approve', {}, true); }
function rejectContact(id) { return request('POST', '/api/directory/me/contact-requests/' + encodeURIComponent(id) + '/reject', {}, true); }
function revokeContact(id) { return request('POST', '/api/directory/me/contact-requests/' + encodeURIComponent(id) + '/revoke', {}, true); }
function getGrantedContact(id) { return request('GET', '/api/directory/me/contact-grants/' + encodeURIComponent(id), {}, true); }
function listMyNeeds() { return request('GET', '/api/directory/me/needs', {}, true); }
function withdrawNeed(id) { return request('DELETE', '/api/directory/me/needs/' + encodeURIComponent(id), {}, true); }
function listMatchedNeeds() { return request('GET', '/api/directory/me/matched-needs', {}, true); }
function respondToNeed(id) { return request('POST', '/api/directory/needs/' + encodeURIComponent(id) + '/respond', {}, true); }
function reportProfile(id, payload) { return request('POST', '/api/directory/profiles/' + encodeURIComponent(id) + '/reports', payload, true); }

function createNeed(payload) {
  return request('POST', '/api/directory/needs', payload, true);
}

function listNotifications() {
  return request('GET', '/api/directory/notifications', {}, true);
}

function markNotificationRead(id) {
  return request('POST', '/api/directory/notifications/' + encodeURIComponent(id) + '/read', {}, true);
}

module.exports = {
  listOptions,
  listProfiles,
  getProfile,
  getMyProfile,
  createProfile,
  updateProfile,
  pauseProfile,
  resumeProfile,
  deleteProfile,
  requestContact,
  listContactRequests,
  approveContact,
  rejectContact,
  revokeContact,
  getGrantedContact,
  listMyNeeds,
  withdrawNeed,
  listMatchedNeeds,
  respondToNeed,
  reportProfile,
  createNeed,
  listNotifications,
  markNotificationRead
};
