/* 语音朗读引擎测试：加载真实 webapp/static/tts.js，mock speechSynthesis，
 * 验证从指定句开始朗读、逐句推进、停止作废等核心行为。
 */
'use strict';

const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const src = fs.readFileSync(path.join(__dirname, '..', 'webapp', 'static', 'tts.js'), 'utf8');

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

console.log('test_tts.js 全部通过');
