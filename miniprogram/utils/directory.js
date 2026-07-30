// Pure directory helpers kept dependency-free for first-compile stability.

function buildDirectoryQuery(filters) {
  const result = {};
  Object.keys(filters || {}).forEach((key) => {
    const value = filters[key];
    if (value !== '' && value !== null && typeof value !== 'undefined') {
      result[key] = value;
    }
  });
  return result;
}

function profileRank(item) {
  const languages = item.language_codes || [];
  return [
    languages.indexOf('vi') >= 0 ? 0 : 1,
    -(Number(item.completeness_score) || 0),
    String(item.id || '')
  ];
}

function compareRank(left, right) {
  const a = profileRank(left);
  const b = profileRank(right);
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] < b[i]) return -1;
    if (a[i] > b[i]) return 1;
  }
  return 0;
}

function mergeAndSortProfiles(profiles) {
  return (profiles || []).slice().sort(compareRank);
}

module.exports = { buildDirectoryQuery, mergeAndSortProfiles, compareRank };
