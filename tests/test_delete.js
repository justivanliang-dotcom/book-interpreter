/* 书籍删除功能测试：加载真实 app.js + tts.js，mock fetch/localStorage/DOM，
 * 验证：每本书带删除按钮、取消确认不删除、删除非当前书保留视图、
 * 删除当前书重置视图并清除"上次打开"记录、全部删除后回到空状态。
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
  if (sel === '.book-list-item') return cls.indexOf('book-list-item') >= 0;
  if (sel === '.book-list-title') return cls.indexOf('book-list-title') >= 0;
  if (sel === '.book-list-del') return cls.indexOf('book-list-del') >= 0;
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
  el.appendChild = function (c) { this.children.push(c); return c; };
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

let books = [
  {
    id: 'b1', title: '书籍甲', filename: 'a.md',
    chapters: [{ title: '一章', has_summary: false, summary_ratio: null, has_plain: false, plain_ratio: null }],
  },
  {
    id: 'b2', title: '书籍乙', filename: 'b.md',
    chapters: [{ title: '一章', has_summary: false, summary_ratio: null, has_plain: false, plain_ratio: null }],
  },
];
let fetchCalls = [];
function okJson(data) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(data) });
}

function fetchMock(url, options) {
  options = options || {};
  fetchCalls.push({ url, options });
  if (url === '/api/tts/status') return okJson({ available: false });
  if (url === '/api/books' && (!options.method || options.method === 'GET')) {
    return okJson(books);
  }
  const delMatch = url.match(/^\/api\/books\/([^/]+)$/);
  if (delMatch && options.method === 'DELETE') {
    books = books.filter((b) => b.id !== delMatch[1]);
    return okJson({ ok: true });
  }
  return okJson({});
}

const localStorageMock = {
  _data: { book_interpreter_last: 'b1' },
  getItem(key) { return key in this._data ? this._data[key] : null; },
  setItem(key, val) { this._data[key] = String(val); },
  removeItem(key) { delete this._data[key]; },
};

const speechMock = { speak() {}, cancel() {}, getVoices() { return []; } };

let confirmResult = true;
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
    confirm() { return confirmResult; },
  },
};
vm.createContext(context);
vm.runInContext(ttsSrc, context, { filename: 'tts.js' });
vm.runInContext(appSrc, context, { filename: 'app.js' });

const tick = () => new Promise((r) => setTimeout(r, 20));
const flush = async (n) => { for (let i = 0; i < (n || 3); i++) await tick(); };
function delCount() {
  return fetchCalls.filter((c) => c.options.method === 'DELETE').length;
}

(async () => {
  // 1. 页面加载 → 恢复 2 本书并自动打开上次的书籍甲
  await flush();
  assert.strictEqual(els['book-card'].hidden, false, '应自动打开上次的书');
  assert.strictEqual(els['book-title'].textContent, '书籍甲');
  const items = documentMock.body.queryAll('.book-list-item');
  assert.strictEqual(items.length, 2, '应显示 2 本已上传书籍');
  items.forEach((li) => {
    assert.ok(li.querySelector('.book-list-del'), '每本书都应有删除按钮');
  });

  // 2. 删除非当前打开的书（书籍乙）→ 视图保持、列表刷新为 1 本
  const delB2 = items[1].querySelector('.book-list-del');
  delB2.click();
  await flush();
  assert.strictEqual(delCount(), 1, '应发起 1 次 DELETE 请求');
  assert.strictEqual(documentMock.body.queryAll('.book-list-item').length, 1, '列表应刷新为 1 本');
  assert.strictEqual(els['book-card'].hidden, false, '删除非当前书不应关闭当前视图');
  assert.strictEqual(els['book-title'].textContent, '书籍甲', '当前打开的书应保持不变');
  assert.strictEqual(localStorageMock.getItem('book_interpreter_last'), 'b1', '上次打开记录应保持');

  // 3. 取消确认 → 不发起删除请求
  confirmResult = false;
  const delB1 = documentMock.body.queryAll('.book-list-del')[0];
  delB1.click();
  await tick();
  assert.strictEqual(delCount(), 1, '取消确认不应发起 DELETE 请求');
  assert.strictEqual(documentMock.body.queryAll('.book-list-item').length, 1, '取消后列表不变');

  // 4. 确认删除当前打开的书（书籍甲）→ 视图重置、last 清除、回到空状态
  confirmResult = true;
  delB1.click();
  await flush();
  assert.strictEqual(delCount(), 2, '确认后应发起 DELETE 请求');
  assert.strictEqual(documentMock.body.queryAll('.book-list-item').length, 0, '全部删除后列表为空');
  assert.strictEqual(els['saved-books'].hidden, true, '无书时列表区应隐藏');
  assert.strictEqual(els['empty-state'].hidden, false, '全部删除后应显示空状态提示');
  assert.strictEqual(els['book-card'].hidden, true, '删除当前书应关闭书籍视图');
  assert.strictEqual(localStorageMock.getItem('book_interpreter_last'), null, '应清除上次打开记录');

  console.log('test_delete.js 全部通过');
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
