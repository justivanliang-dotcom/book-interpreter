/* 全页拖放上传逻辑测试：加载真实 webapp/static/app.js，模拟 DOM 与拖放事件序列。
 *
 * 回归重点（修复的 bug）：
 * 1. dragover 拖动期间高频触发，绝不能参与 dragDepth 计数，
 *    否则计数失衡、drop 后提示层残留导致上传无响应。
 * 2. drop 时强制归零并隐藏提示层，任何情况下松手后提示层必然消失、触发上传。
 */
'use strict';

const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const src = fs.readFileSync(path.join(__dirname, '..', 'webapp', 'static', 'app.js'), 'utf8');

function mockEl() {
  return {
    hidden: false,
    textContent: '',
    className: '',
    innerHTML: '',
    value: '',
    disabled: false,
    dataset: {},
    classList: { add() {}, remove() {}, contains() { return false; } },
    appendChild() {},
    addEventListener() {},
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
}

const handlers = {};
const els = {};

const documentMock = {
  getElementById(id) { return els[id] || (els[id] = mockEl()); },
  createElement() { return mockEl(); },
  createTextNode() { return {}; },
  addEventListener(type, fn) { (handlers[type] = handlers[type] || []).push(fn); },
  body: {
    appendChild(el) {
      if (el && el.className === 'drop-overlay') documentMock._overlay = el;
    },
  },
};

function dispatch(type, evt) {
  const e = Object.assign({ preventDefault() {}, dataTransfer: null }, evt);
  for (const fn of handlers[type] || []) fn(e);
}

let fetchCalls = 0;
function fetchMock() {
  fetchCalls++;
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve({ id: 'b1', title: '测试书', filename: 'a.epub', chapters: [] }),
  });
}
class FormDataMock { append() {} }

const localStorageMock = {
  _data: {},
  getItem(key) { return key in this._data ? this._data[key] : null; },
  setItem(key, val) { this._data[key] = String(val); },
};

const context = { document: documentMock, fetch: fetchMock, FormData: FormDataMock, localStorage: localStorageMock, console };
vm.createContext(context);
vm.runInContext(src, context, { filename: 'app.js' });

const overlay = documentMock._overlay;
assert.ok(overlay, '拖放提示层应被创建');

(async () => {
  // 1. 初始状态：提示层隐藏
  assert.strictEqual(overlay.hidden, true, '初始提示层应隐藏');

  // 2. 拖入文件：dragenter 显示提示层
  dispatch('dragenter');
  assert.strictEqual(overlay.hidden, false, '拖入后提示层应显示');

  // 3. 拖动过程中 dragover 高频触发（模拟鼠标移动），提示层保持显示、计数不受影响
  for (let i = 0; i < 1000; i++) dispatch('dragover');
  assert.strictEqual(overlay.hidden, false, '拖动过程中提示层应保持显示');

  // 4. 与 dragenter 配对的 dragleave 全部离开后，提示层归零隐藏
  dispatch('dragleave');
  assert.strictEqual(overlay.hidden, true, '拖离窗口后提示层应隐藏');

  // 5. 再次拖入并松开：drop 强制隐藏提示层并触发上传
  dispatch('dragenter');
  assert.strictEqual(overlay.hidden, false, '再次拖入提示层应显示');
  dispatch('drop', { dataTransfer: { files: [{ name: 'book.epub', size: 100 }] } });
  assert.strictEqual(overlay.hidden, true, 'drop 后提示层必须立即隐藏');
  assert.strictEqual(fetchCalls, 1, 'drop 后应发起上传请求');

  // 6. 等待异步上传完成，状态提示更新
  await new Promise((r) => setTimeout(r, 20));
  assert.ok(
    els['upload-status'] && els['upload-status'].textContent.includes('解析完成'),
    '上传完成后应显示解析完成状态，实际为: ' + (els['upload-status'] && els['upload-status'].textContent)
  );

  // 7. 无文件的 drop（拖入文本等）不发起上传，但提示层仍隐藏
  dispatch('dragenter');
  dispatch('drop', { dataTransfer: { files: [] } });
  assert.strictEqual(overlay.hidden, true, '无文件 drop 提示层也应隐藏');
  assert.strictEqual(fetchCalls, 1, '无文件 drop 不应发起上传');

  console.log('test_dragdrop.js 全部通过');
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
