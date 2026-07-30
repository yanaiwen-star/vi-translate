// utils/lang-detect.js
// 简单的语种检测辅助（兜底用，主识别由 ASR 引擎返回）

/**
 * 通过字符特征判断字符串可能语种
 * 仅作兜底，主要以 ASR 返回结果为准
 * @param {string} text
 * @returns {'zh' | 'vie' | 'unknown'}
 */
function detectByChars(text) {
  if (!text) return 'unknown';

  // 越南语特有字符：ă â ê ô ơ ư đ + 各种带变音符的字母
  const vietnamesePattern = /[ăâđêôơưĂÂĐÊÔƠƯàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]/;

  // 中文字符
  const chinesePattern = /[\u4e00-\u9fff]/;

  if (vietnamesePattern.test(text)) return 'vie';
  if (chinesePattern.test(text)) return 'zh';

  // 拉丁字母但无变音符 → 不确定
  return 'unknown';
}

/**
 * 语种显示名
 */
function langName(lang) {
  const map = {
    zh: '中文',
    vie: 'Tiếng Việt',
    zh_vie: '中文 ⇄ Tiếng Việt',
    unknown: '未知'
  };
  return map[lang] || lang;
}

/**
 * 语种对应的国旗 emoji
 */
function langFlag(lang) {
  const map = {
    zh: '🇨🇳',
    vie: '🇻🇳'
  };
  return map[lang] || '🌐';
}

module.exports = {
  detectByChars,
  langName,
  langFlag
};