// components/lang-badge/lang-badge.js
const langUtil = require('../../utils/lang-detect.js');

Component({
  properties: {
    lang: { type: String, value: 'zh' },
    small: { type: Boolean, value: false }
  },
  data: {
    name: '',
    flag: ''
  },
  observers: {
    'lang': function(lang) {
      this.setData({
        name: langUtil.langName(lang),
        flag: langUtil.langFlag(lang)
      });
    }
  },
  lifetimes: {
    attached() {
      this.setData({
        name: langUtil.langName(this.data.lang),
        flag: langUtil.langFlag(this.data.lang)
      });
    }
  }
});