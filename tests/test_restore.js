/* 页面恢复测试：加载真实 app.js + tts.js，mock fetch/localStorage/DOM，
 * 验证：页面加载后恢复已上传书籍列表、自动打开上次的书、
 * 展开章节时自动拉取上次落盘的浓缩与讲解缓存、比例下拉恢复上次值。
 */
'use strict';

const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ttsSrc = fs.readFileSync(path.join(__dirname, '..', 'webapp', 'static', 'tts.js'), 'utf8');
const appSrc = fs.readFileSync(path.join(__dirname, '..', 'webapp', 'static', 'app.js'), 'utf8');

function matches(el, sel) {
  const cls = (el.className || '').split(' ').filter(Boolean);
  const m = sel.match(/^li\[data-index="(\d+)"\]$/);
  if (m) return el.tag === 'li' && String(el.dataset.index) === m[1];
  if (sel === '.book-list-item') return cls.indexOf('book-list-item') >= 0;
  if (sel === '.book-list-title') return cls.indexOf('book-list-title') >= 0;
  if (sel === '.chapter-item') return cls.indexOf('chapter-item') >= 0;
  if (sel === '.chapter-expand') return cls.indexOf('chapter-expand') >= 0;
  if (sel === '.chapter-summary') return cls.indexOf('chapter-summary') >= 0;
  if (sel === '.chapter-plain') return cls.indexOf('chapter-plain') >= 0;
  if (sel === '.chapter-ratio') return cls.indexOf('chapter-ratio') >= 0;
  if (sel === '.chapter-head') return cls.indexOf('chapter-head') >= 0;
  if (sel === '.summarize-btn') return cls.indexOf('summarize-btn') >= 0;
  if (sel === '.plain-btn') return cls.indexOf('plain-btn') >= 0;
  if (sel === '.progress-wrap') return cls.indexOf('progress-wrap') >= 0;
  if (sel === '.sentence-wrap') return cls.indexOf('sentence-wrap') >= 0;
  if (sel === '.plain-body') return cls.indexOf('plain-body') >= 0;
  if (sel === '.speak-bar') return cls.indexOf('speak-bar') >= 0;
  return false;
}

function makeEl(tag) {
  const el = {
    tag: tag || 'div',
    children: [],
    _handlers: {},
    _text: '',
    _html: '',
    hidden: false,
    className: '',
    style: {},
    value: '0.1',
    disabled: false,
    dataset: {},
    files: [],
    classList: {
      _s: {},
      add(c) { this._s[c] = 1; },
      remove(c) { delete this._s[c]; },
      contains(c) { return !!this._s[c]; },
    },
  };
  Object.defineProperty(el, 'innerHTML', {
    get() { return this._html; },
    set(v) { this._html = v; this.children = []; },
  });
  Object.defineProperty(el, 'textContent', {
    get() { return this._text; },
    set(v) { this._text = String(v); },
  });
  el.appendChild = function (c) {
    this.children.push(c);
    if (c.tag === 'option' && c.selected) this.value = c.value;
    return c;
  };
  el.addEventListener = function (t, fn) {
    (this._handlers[t] = this._handlers[t] || []).push(fn);
  };
  el.getBoundingClientRect = function () {
    return { left: 0, top: 0, bottom: 0, right: 0, width: 0, height: 0 };
  };
  el.click = function (evt) {
    const e = Object.assign({ preventDefault() {}, stopPropagation() {} }, evt || {});
    (this._handlers.click || []).forEach(function (fn) { fn(e); });
  };
  el.queryAll = function (sel) {
    const out = [];
    (function walk(node) {
      (node.children || []).forEach(function (c) {
        if (matches(c, sel)) out.push(c);
        walk(c);
      });
    }(this));
    return out;
  };
  el.querySelectorAll = function (sel) { return el.queryAll(sel); };
  el.querySelector = function (sel) { return el.queryAll(sel)[0] || null; };
  return el;
}

const els = {};
const root = makeEl('body');

const documentMock = {
  getElementById(id) {
    if (!els[id]) {
      els[id] = makeEl('div');
      root.appendChild(els[id]);
    }
    return els[id];
  },
  createElement(tag) { return makeEl(tag); },
  createTextNode() { return {}; },
  addEventListener() {},
  body: root,
  querySelectorAll(sel) { return root.queryAll(sel); },
  querySelector(sel) { return root.queryAll(sel)[0] || null; },
};

let fetchCalls = [];
function okJson(data) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(data) });
}

// 模拟服务端落盘数据：上次上传了书，第 1 章有 50% 浓缩与 25% 讲解缓存
const savedBook = {
  id: 'b1',
  title: '测试书',
  filename: 'a.md',
  chapters: [
    { title: '第一章', has_summary: true, summary_ratio: 0.5, has_plain: true, plain_ratio: 0.25 },
    { title: '第二章', has_summary: false, summary_ratio: null, has_plain: false, plain_ratio: null },
  ],
};

function fetchMock(url, options) {
  options = options || {};
  fetchCalls.push({ url, options });
  if (url === '/api/tts/status') {
    return okJson({ available: false });
  }
  if (url === '/api/books' && (!options.method || options.method === 'GET')) {
    return okJson([savedBook]);
  }
  if (url.indexOf('/summarize') >= 0) {
    return okJson({
      title: '第一章',
      summary: '摘要全文',
      sentences: [
        { text: '句子一。', para: 0, context: '原文一', source: 's1' },
        { text: '句子二。', para: 0, context: '原文二', source: 's2' },
      ],
      word_count: 8,
      target_words: 10,
    });
  }
  if (url.indexOf('/plain') >= 0) {
    return okJson({ title: '第一章', text: '讲解句一。讲解句二！' });
  }
  return okJson({});
}

const localStorageMock = {
  _data: { book_interpreter_last: 'b1' },
  getItem(key) { return key in this._data ? this._data[key] : null; },
  setItem(key, val) { this._data[key] = String(val); },
};

const speechMock = {
  speak() {},
  cancel() {},
  getVoices() { return []; },
};

const context = {
  document: documentMock,
  fetch: fetchMock,
  FormData: class { append() {} },
  localStorage: localStorageMock,
  SpeechSynthesisUtterance: function (text) { this.text = text; },
  setTimeout,
  clearTimeout,
  console,
  window: {
    speechSynthesis: speechMock,
    location: { href: '' },
  },
};
vm.createContext(context);
vm.runInContext(ttsSrc, context, { filename: 'tts.js' });
vm.runInContext(appSrc, context, { filename: 'app.js' });

const tick = () => new Promise((r) => setTimeout(r, 20));
const flush = async (n) => { for (let i = 0; i < (n || 3); i++) await tick(); };

(async () => {
  // 1. 页面加载后应拉取书籍列表并显示"已上传书籍"
  await flush();
  const listReq = fetchCalls.find((c) => c.url === '/api/books' && !c.options.method);
  assert.ok(listReq, '页面加载时应请求 GET /api/books 恢复列表');
  assert.strictEqual(els['saved-books'].hidden, false, '有已上传书籍时列表区应显示');
  const bookItems = documentMock.body.queryAll('.book-list-item');
  assert.strictEqual(bookItems.length, 1, '应显示 1 本已上传书籍');
  assert.strictEqual(bookItems[0].querySelector('.book-list-title').textContent, '测试书');

  // 2. localStorage 记录上次打开的书 → 自动打开并渲染章节
  assert.strictEqual(els['book-card'].hidden, false, '应自动打开上次的书');
  assert.strictEqual(els['book-title'].textContent, '测试书');
  const li0 = els['chapter-list'].querySelector('li[data-index="0"]');
  const li1 = els['chapter-list'].querySelector('li[data-index="1"]');
  assert.ok(li0 && li1, '应渲染全部章节');

  // 3. 第 1 章比例下拉应恢复上次的 50%
  const select0 = li0.querySelector('.chapter-ratio');
  assert.strictEqual(select0.value, '0.5', '比例下拉应恢复上次浓缩比例');
  const select1 = li1.querySelector('.chapter-ratio');
  assert.strictEqual(select1.value, '0.1', '无缓存章节比例保持默认');

  // 4. 展开第 1 章 → 自动拉取上次的浓缩与讲解缓存
  li0.querySelector('.chapter-head').click();
  await flush();
  const summaryBox = li0.querySelector('.chapter-summary');
  assert.strictEqual(summaryBox.queryAll('.sentence-wrap').length, 2, '应自动渲染上次浓缩的句子');
  const plainBox = li0.querySelector('.chapter-plain');
  assert.strictEqual(plainBox.hidden, false, '讲解框应可见');
  assert.strictEqual(plainBox.queryAll('.sentence-wrap').length, 2, '应自动渲染上次讲解的句子');

  // 5. 请求应按上次的比例发起（浓缩 0.5、讲解 0.25），且只各发起一次
  const sumCalls = fetchCalls.filter((c) => c.url.indexOf('/summarize') >= 0);
  const plainCalls = fetchCalls.filter((c) => c.url.indexOf('/plain') >= 0);
  assert.strictEqual(sumCalls.length, 1, '浓缩缓存应只请求一次');
  assert.ok(sumCalls[0].url.indexOf('ratio=0.5') >= 0, '浓缩应按上次比例 0.5 请求');
  assert.strictEqual(plainCalls.length, 1, '讲解缓存应只请求一次');
  assert.ok(plainCalls[0].url.indexOf('ratio=0.25') >= 0, '讲解应按上次比例 0.25 请求');

  // 6. 展开无缓存的第 2 章 → 不自动请求，显示提示
  li1.querySelector('.chapter-head').click();
  await tick();
  const sumBefore = fetchCalls.filter((c) => c.url.indexOf('/summarize') >= 0).length;
  assert.strictEqual(sumBefore, 1, '无缓存章节不应自动发起浓缩请求');
  const hint = li1.querySelector('.chapter-summary');
  assert.ok(hint._html.indexOf('浓缩本章') >= 0, '无缓存章节应显示生成提示');

  // 7. 点击书籍列表项可切换到该书（模拟列表恢复）
  bookItems[0].click();
  assert.strictEqual(els['book-card'].hidden, false, '点击列表项应打开该书');
  assert.strictEqual(localStorageMock.getItem('book_interpreter_last'), 'b1');

  console.log('test_restore.js 全部通过');
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
