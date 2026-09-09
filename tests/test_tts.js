/* 语音朗读引擎测试：加载真实 webapp/static/tts.js，
 * 1) 浏览器语音回退模式：mock speechSynthesis，验证从指定句开始朗读、逐句推进、停止。
 * 2) 豆包在线语音模式：mock fetch/Audio/URL，验证批量预取、逐句播放、失败回退。
 */
'use strict';

const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const src = fs.readFileSync(path.join(__dirname, '..', 'webapp', 'static', 'tts.js'), 'utf8');

const b64 = (s) => Buffer.from(s, 'utf8').toString('base64');
const tick = () => new Promise((r) => setTimeout(r, 5));

// ---------- 浏览器回退模式 ----------
const spoken = [];
const utterances = [];
let cancelCount = 0;
const speechMock = {
  speak(u) { utterances.push(u); spoken.push(u.text); },
  cancel() { cancelCount++; },
};

const context = {
  window: { speechSynthesis: speechMock },
  SpeechSynthesisUtterance: function (text) { this.text = text; },
};
vm.createContext(context);
vm.runInContext(src, context, { filename: 'tts.js' });
const TTS = context.window.TTS;

(async () => {
  // 1. 能力检测
  assert.strictEqual(TTS.supported, true, '应检测到 speechSynthesis');

  // 2. 从第 2 句开始朗读，回调顺序正确
  const events = [];
  spoken.length = 0;
  TTS.speakFrom(['一。', '二。', '三。', '四。'], 1, {
    onStart: (i) => events.push(['start', i]),
    onProgress: (i) => events.push(['progress', i]),
    onEnd: () => events.push(['end']),
  });
  assert.deepStrictEqual(spoken.slice(), ['二。'], '应从第 2 句开始朗读');
  assert.deepStrictEqual(events, [['start', 1], ['progress', 1]], '开始与进度回调应携带正确索引');

  // 3. 每句读完自动推进到下一句
  utterances[0].onend();
  assert.deepStrictEqual(spoken.slice(), ['二。', '三。'], 'onend 后应朗读下一句');

  // 4. 读到末尾触发 onEnd
  utterances[1].onend();
  utterances[2].onend();
  assert.deepStrictEqual(
    events.slice(1),
    [['progress', 1], ['progress', 2], ['progress', 3], ['end']],
    '应依次推进并在末尾触发 end'
  );

  // 5. stop 后旧 utterance 的 onend 不再推进
  spoken.length = 0;
  TTS.speakFrom(['一。', '二。'], 0);
  TTS.stop();
  const nAfterStop = spoken.length;
  const lastIdx = utterances.length - 1;
  assert.ok(cancelCount > 0, 'stop 应调用 speechSynthesis.cancel');
  utterances[lastIdx].onend();
  assert.strictEqual(spoken.length, nAfterStop, 'stop 后不应继续朗读');

  // 6. 越界 start 自动归 0
  spoken.length = 0;
  TTS.speakFrom(['一。', '二。'], 99);
  assert.deepStrictEqual(spoken.slice(), ['一。'], '越界 start 应从第 1 句开始');

  // 7. 空内容不朗读
  spoken.length = 0;
  TTS.speakFrom([], 0);
  TTS.speakFrom(['  ', null, ''], 0);
  assert.strictEqual(spoken.length, 0, '空句子不应朗读');

  // 8. 未支持环境：onUnsupported 回调
  const ctx2 = { window: {}, SpeechSynthesisUtterance: function (t) { this.text = t; } };
  vm.createContext(ctx2);
  vm.runInContext(src, ctx2, { filename: 'tts.js' });
  let unsupportedFired = false;
  ctx2.window.TTS.speakFrom(['x'], 0, { onUnsupported: () => { unsupportedFired = true; } });
  assert.strictEqual(ctx2.window.TTS.supported, false, '无 speechSynthesis 应不支持');
  assert.ok(unsupportedFired, '不支持时应回调 onUnsupported');

  // ---------- 豆包在线语音模式 ----------
  const audioInstances = [];
  const fetchCalls = [];
  const fetchMock = (url, options) => {
    options = options || {};
    fetchCalls.push({ url, options });
    if (url === '/api/tts/status') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ available: true }) });
    }
    if (url === '/api/tts/batch') {
      const texts = (JSON.parse(options.body).texts || []);
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ audios: texts.map((t) => b64(t)) }),
      });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  };

  class AudioMock {
    constructor() {
      this.src = '';
      this.preload = '';
      this.onended = null;
      this.onerror = null;
      this.playCalls = 0;
      audioInstances.push(this);
    }
    play() { this.playCalls++; return Promise.resolve(); }
    pause() { this.paused = true; }
    removeAttribute() { this.src = ''; }
  }

  const ctx3 = {
    window: {
      fetch: fetchMock,
      speechSynthesis: speechMock,
    },
    localStorage: {
      getItem: (k) => (k === 'book_interpreter_token' ? 't123' : null),
    },
    SpeechSynthesisUtterance: function (text) { this.text = text; },
    Audio: AudioMock,
    URL: { createObjectURL: () => 'blob:mock-audio', revokeObjectURL: () => {} },
    atob: (s) => Buffer.from(s, 'base64').toString('binary'),
    Blob: globalThis.Blob,
  };
  vm.createContext(ctx3);
  vm.runInContext(src, ctx3, { filename: 'tts.js' });
  const TTS3 = ctx3.window.TTS;

  // 9. 探测后端豆包可用
  await new Promise((resolve) => TTS3.probeServer(resolve));
  assert.strictEqual(fetchCalls.some((c) => c.url === '/api/tts/status'), true, '应探测 /api/tts/status');

  // 10. 服务器模式：从第 1 句开始，预取并播放，逐句推进
  const ev3 = [];
  audioInstances.length = 0;
  TTS3.speakFrom(['一。', '二。', '三。', '四。', '五。', '六。', '七。', '八。', '九。'], 1, {
    onStart: (i) => ev3.push(['start', i]),
    onProgress: (i) => ev3.push(['progress', i]),
    onEnd: () => ev3.push(['end']),
  });
  await tick();
  assert.deepStrictEqual(ev3, [['start', 1], ['progress', 1]], '应从第 2 句开始并播报进度');
  assert.strictEqual(fetchCalls.filter((c) => c.url === '/api/tts/batch').length, 1,
    '9 句从第 2 句起 8 句一批仅需 1 批');
  const batch1 = fetchCalls.find((c) => c.url === '/api/tts/batch' && c.options.body.includes('二。'));
  assert.ok(batch1, '第一批应包含第 2 句');
  assert.strictEqual(
    batch1.options.headers['X-Access-Token'],
    't123',
    'batch 请求应携带访问口令，否则服务器 401 会回退浏览器机械声'
  );
  assert.strictEqual(audioInstances.length, 1, '应创建唯一 Audio 实例');
  assert.strictEqual(audioInstances[0].src, 'blob:mock-audio', '应加载预取音频');
  assert.strictEqual(audioInstances[0].playCalls, 1, '应开始播放');

  // 11. 播放完推进到下一句
  audioInstances[0].onended();
  await tick();
  assert.strictEqual(audioInstances[0].playCalls, 2, 'onended 后应播放下一句');
  assert.deepStrictEqual(
    ev3.slice(1),
    [['progress', 1], ['progress', 2]],
    '推进后应播报第 3 句进度'
  );

  // 12. 从第 1 句起 9 句分 2 批预取（8+1）
  const batchesBefore = fetchCalls.filter((c) => c.url === '/api/tts/batch').length;
  TTS3.stop();
  TTS3.speakFrom(['一。', '二。', '三。', '四。', '五。', '六。', '七。', '八。', '九。'], 0, {});
  await tick();
  assert.strictEqual(
    fetchCalls.filter((c) => c.url === '/api/tts/batch').length - batchesBefore,
    2,
    '9 句从第 1 句起应分 2 批预取（8+1）'
  );

  // 13. 服务器模式下 stop 停止播放并清理
  TTS3.stop();
  assert.ok(audioInstances[0].paused === true, 'stop 应暂停音频');

  // 14. 服务器模式单句失败 → 跳过该句继续下一句，不整体回退机械声
  spoken.length = 0;
  audioInstances.length = 0;
  let batchFailIndex = 0; // 第 0 批失败
  const ctx4 = {
    window: {
      fetch: (url, options) => {
        if (url === '/api/tts/status') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ available: true }) });
        }
        if (url === '/api/tts/batch') {
          if (batchFailIndex === 0) {
            batchFailIndex++;
            return Promise.reject(new Error('batch 0 failed'));
          }
          const texts = JSON.parse(options.body).texts || [];
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ audios: texts.map((t) => b64(t)) }),
          });
        }
        return Promise.reject(new Error('network down'));
      },
      speechSynthesis: speechMock,
    },
    localStorage: { getItem: () => 't123' },
    SpeechSynthesisUtterance: function (text) { this.text = text; },
    Audio: AudioMock,
    URL: { createObjectURL: () => 'blob:x', revokeObjectURL: () => {} },
    atob: (s) => Buffer.from(s, 'base64').toString('binary'),
    Blob: globalThis.Blob,
  };
  vm.createContext(ctx4);
  vm.runInContext(src, ctx4, { filename: 'tts.js' });
  const TTS4 = ctx4.window.TTS;
  await new Promise((resolve) => TTS4.probeServer(resolve));
  // 8 句话（2 批，每批 5/3）：第一批失败 → 应跳过 5 句继续第二批
  const items8 = [];
  for (let i = 0; i < 8; i++) items8.push('句' + i + '。');
  TTS4.speakFrom(items8, 0, {});
  await tick();
  await tick();
  // 第一批 5 句失败被跳过，不应触发浏览器语音
  assert.deepStrictEqual(spoken.slice(), [], '单批失败不应回退浏览器机械声');
  // 第二批（句 5、6、7）应正常播放
  assert.ok(audioInstances.length >= 1, '第二批应继续服务器语音播放');

  // 15. 语音选择：只在普通话（zh-CN）里挑女声，绝不选粤语/台湾
  const ctx5 = {
    window: {
      speechSynthesis: {
        getVoices: () => [
          { lang: 'zh-HK', name: 'Sinji - 粤語（香港）' },
          { lang: 'zh-TW', name: '美佳 - 中文（台湾）' },
          { lang: 'zh-CN', name: 'Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)' },
          { lang: 'zh-CN', name: 'Microsoft Huihui - Chinese (Simplified, PRC)' },
        ],
      },
    },
    SpeechSynthesisUtterance: function (text) { this.text = text; },
  };
  vm.createContext(ctx5);
  vm.runInContext(src, ctx5, { filename: 'tts.js' });
  const picked = ctx5.window.TTS.pickVoice();
  assert.ok(picked, '应选到普通话语音');
  assert.strictEqual(picked.lang, 'zh-CN', '必须选普通话 zh-CN，不得选粤语/台湾');
  assert.ok(/xiaoxiao/i.test(picked.name), '自然女声（晓晓）应优先于普通普通话女声');

  // 16. 只有粤语没有普通话时：宁可不用语音，也不读粤语
  const ctx6 = {
    window: {
      speechSynthesis: {
        getVoices: () => [
          { lang: 'zh-HK', name: 'Sinji - 粵語（香港）' },
          { lang: 'zh-HK', name: 'Tracy - 粵語（香港）' },
        ],
      },
    },
    SpeechSynthesisUtterance: function (text) { this.text = text; },
  };
  vm.createContext(ctx6);
  vm.runInContext(src, ctx6, { filename: 'tts.js' });
  assert.strictEqual(ctx6.window.TTS.pickVoice(), null, '无普通话语音时应返回 null，绝不选粤语');

  // 17. 探测失败后恢复：再次朗读时强制重探测，成功后走服务器自然女声
  let statusFlip = false;
  const ctx7 = {
    window: {
      fetch: (url, options) => {
        if (url === '/api/tts/status') {
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ available: statusFlip }) });
        }
        if (url === '/api/tts/batch') {
          const texts = (JSON.parse(options.body).texts || []);
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ audios: texts.map((t) => b64(t)) }),
          });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      },
      speechSynthesis: speechMock,
    },
    SpeechSynthesisUtterance: function (text) { this.text = text; },
    Audio: AudioMock,
    URL: { createObjectURL: () => 'blob:mock-audio', revokeObjectURL: () => {} },
    atob: (s) => Buffer.from(s, 'base64').toString('binary'),
    Blob: globalThis.Blob,
  };
  vm.createContext(ctx7);
  vm.runInContext(src, ctx7, { filename: 'tts.js' });
  const TTS7 = ctx7.window.TTS;
  await new Promise((r) => TTS7.probeServer(r));
  assert.strictEqual(statusFlip, false, '首轮探测应处于不可用状态');
  // 探测不可用时：回退浏览器语音
  spoken.length = 0;
  TTS7.speakFrom(['回退句。'], 0, {});
  await tick();
  await tick();
  assert.deepStrictEqual(spoken.slice(), ['回退句。'], '探测不可用应回退浏览器语音');
  // 服务器恢复后：再次朗读强制重探测 → 服务器自然女声
  statusFlip = true;
  spoken.length = 0;
  const audioBefore = audioInstances.length;
  TTS7.speakFrom(['服务器句。'], 0, {});
  await tick();
  await tick();
  assert.deepStrictEqual(spoken.slice(), [], '重探测成功应走服务器模式，不再用浏览器语音');
  assert.ok(audioInstances.length > audioBefore, '服务器模式应创建 Audio 播放自然女声');

  console.log('test_tts.js 全部通过');
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
