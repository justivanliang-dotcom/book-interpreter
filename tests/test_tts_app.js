/* 语音朗读前端集成测试：加载真实 tts.js + app.js，mock DOM 与 speechSynthesis，
 * 验证浓缩句子与讲解句子的长按朗读菜单、从指定句开始朗读、朗读高亮与停止。
 */
'use strict';

const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ttsSrc = fs.readFileSync(path.join(__dirname, '..', 'webapp', 'static', 'tts.js'), 'utf8');
const appSrc = fs.readFileSync(path.join(__dirname, '..', 'webapp', 'static', 'app.js'), 'utf8');

const spoken = [];
const utterances = [];
let cancelCount = 0;
const speechMock = {
  speak(u) { utterances.push(u); spoken.push(u.text); },
  cancel() { cancelCount++; },
};

function matches(el, sel) {
  const cls = (el.className || '').split(' ').filter(Boolean);
  if (sel === '.sentence-wrap') return cls.indexOf('sentence-wrap') >= 0;
  if (sel === '.summary-sentence') return cls.indexOf('summary-sentence') >= 0;
  if (sel === '.speak-btn') return cls.indexOf('speak-btn') >= 0;
  if (sel === '.speak-menu') return cls.indexOf('speak-menu') >= 0;
  if (sel === '.speak-all-btn') return cls.indexOf('speak-all-btn') >= 0;
  if (sel === '.speak-bar') return cls.indexOf('speak-bar') >= 0;
  if (sel === '.sentence-wrap.speaking') return cls.indexOf('sentence-wrap') >= 0 && el.classList.contains('speaking');
  const m = sel.match(/^li\[data-index="(\d+)"\]$/);
  if (m) return el.tag === 'li' && String(el.dataset.index) === m[1];
  if (sel === '.chapter-summary') return cls.indexOf('chapter-summary') >= 0;
  if (sel === '.chapter-plain') return cls.indexOf('chapter-plain') >= 0;
  if (sel === '.summarize-btn') return cls.indexOf('summarize-btn') >= 0;
  if (sel === '.plain-btn') return cls.indexOf('plain-btn') >= 0;
  if (sel === '.chapter-ratio') return cls.indexOf('chapter-ratio') >= 0;
  if (sel === '.progress-wrap') return cls.indexOf('progress-wrap') >= 0;
  if (sel === '.btn') return cls.indexOf('btn') >= 0;
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

let fetchCalls = [];
function okJson(data) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(data) });
}
function fetchMock(url, options) {
  options = options || {};
  fetchCalls.push({ url, options });
  if (url === '/api/tts/status') {
    // 测试环境无豆包 API Key，走浏览器语音回退
    return okJson({ available: false });
  }
  if (url === '/api/books' && options.method === 'POST') {
    return okJson({ id: 'b1', title: '测试书', filename: 'a.md', chapters: [{ title: '第一章' }, { title: '第二章' }] });
  }
  if (url === '/api/books' && (!options.method || options.method === 'GET')) {
    // 页面加载时恢复已上传书籍列表
    return okJson([]);
  }
  if (url.indexOf('/summarize') >= 0) {
    return okJson({
      title: '第一章',
      summary: '摘要全文',
      sentences: [
        { text: '句子一。', para: 0, context: '原文一', source: 's1' },
        { text: '句子二。', para: 0, context: '原文二', source: 's2' },
        { text: '句子三。', para: 0, context: '原文三', source: 's3' },
      ],
      word_count: 9,
      target_words: 10,
    });
  }
  if (url.indexOf('/plain') >= 0) {
    return okJson({ title: '第一章', text: '讲解句一。讲解句二！讲解句三？\n第二段句四。' });
  }
  return okJson({});
}

const localStorageMock = {
  _data: {},
  getItem(key) { return key in this._data ? this._data[key] : null; },
  setItem(key, val) { this._data[key] = String(val); },
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
    get speechSynthesis() { return speechMock; },
    location: { href: '' },
  },
};
vm.createContext(context);
vm.runInContext(ttsSrc, context, { filename: 'tts.js' });
assert.ok(context.window.TTS, 'tts.js 应挂载 window.TTS');
vm.runInContext(appSrc, context, { filename: 'app.js' });

const tick = () => new Promise((r) => setTimeout(r, 10));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function findSpeakBar() {
  return documentMock.body.queryAll('.speak-bar')[0] || null;
}

(async () => {
  // 1. 上传书籍 → 渲染章节
  const fi = els['file-input'];
  fi.files = [{ name: 'a.md', size: 3 }];
  (fi._handlers.change || []).forEach((fn) => fn({ target: fi }));
  await tick();
  assert.strictEqual(els['book-card'].hidden, false, '上传后应显示书籍卡片');

  // 2. 点击"浓缩本章" → 渲染句子流（无句内小喇叭，长按弹出朗读菜单）
  const li0 = els['chapter-list'].querySelector('li[data-index="0"]');
  assert.ok(li0, '应有章节条目');
  li0.querySelector('.summarize-btn').click();
  await tick();
  const summaryBox = li0.querySelector('.chapter-summary');
  const wraps = summaryBox.queryAll('.sentence-wrap');
  assert.strictEqual(wraps.length, 3, '浓缩应渲染 3 个句子');
  assert.strictEqual(wraps[0].querySelector('.speak-btn'), null, '句子内不应有小喇叭');

  // 3. 长按第 2 句 → 弹出朗读菜单 → 点"朗读"从第 2 句开始
  spoken.length = 0;
  const span1 = wraps[1].querySelector('.summary-sentence');
  const md = span1._handlers['mousedown'][0];
  md({ clientX: 10, clientY: 10 });
  await sleep(560); // 超过 500ms 长按阈值
  let menu = documentMock.body.queryAll('.speak-menu')[0];
  assert.ok(menu, '长按后应弹出朗读菜单');
  const menuSpeak = menu.queryAll('.btn').find((b) => b.textContent === '朗读');
  assert.ok(menuSpeak, '菜单中应有"朗读"按钮');
  menuSpeak.click();
  assert.deepStrictEqual(spoken.slice(), ['句子二。'], '长按菜单朗读应从第 2 句开始');
  assert.strictEqual(wraps[1].classList.contains('speaking'), true, '正在朗读的句子应高亮');
  const bar = findSpeakBar();
  assert.ok(bar, '朗读时应显示浮动停止条');
  assert.strictEqual(bar.hidden, false, '朗读中停止条应可见');

  // 4. 朗读推进后高亮跟随
  utterances[utterances.length - 1].onend();
  assert.strictEqual(wraps[2].classList.contains('speaking'), true, '推进后高亮应移到下一句');
  assert.strictEqual(wraps[1].classList.contains('speaking'), false, '上一句高亮应清除');

  // 5. 点击"停止" → 取消朗读并隐藏停止条
  bar.querySelector('.btn').click();
  assert.ok(cancelCount > 0, '停止应调用 speechSynthesis.cancel');
  assert.strictEqual(bar.hidden, true, '停止后停止条应隐藏');
  assert.strictEqual(wraps[2].classList.contains('speaking'), false, '停止后高亮应清除');

  // 6. 大白话讲解：拆句渲染，点击句子从该句朗读
  spoken.length = 0;
  li0.querySelector('.plain-btn').click();
  await tick();
  const plainBox = li0.querySelector('.chapter-plain');
  const plainWraps = plainBox.queryAll('.sentence-wrap');
  assert.strictEqual(plainWraps.length, 4, '讲解应按标点拆为 4 句');
  const allBtn = plainBox.querySelector('.speak-all-btn');
  assert.ok(allBtn, '讲解多句时应显示"朗读全部"按钮');
  plainWraps[2].querySelector('.summary-sentence').click();
  assert.deepStrictEqual(spoken.slice(), ['讲解句三？'], '点击讲解第 3 句应从该句朗读');

  // 7. "朗读全部"从第 1 句开始
  spoken.length = 0;
  allBtn.click();
  assert.deepStrictEqual(spoken.slice(), ['讲解句一。'], '"朗读全部"应从第 1 句开始');

  console.log('test_tts_app.js 全部通过');
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
