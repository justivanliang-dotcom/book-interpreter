/* 语音朗读引擎：基于 Web Speech API，支持从指定句子开始顺序朗读。
 * 逐句调用 speechSynthesis，天然规避 Chrome 长文本截断问题，
 * 且每次 onend 后推进，便于调用方高亮当前句。
 */
(function () {
  var supported = typeof window !== 'undefined' && 'speechSynthesis' in window;
  var runId = 0;

  function normItems(sentences) {
    return (sentences || [])
      .map(function (s) { return typeof s === 'string' ? s : (s && s.text ? s.text : ''); })
      .filter(function (t) { return t && t.trim(); });
  }

  function speakFrom(sentences, start, opts) {
    opts = opts || {};
    stop();
    if (!supported) {
      if (opts.onUnsupported) opts.onUnsupported();
      return;
    }
    var items = normItems(sentences);
    if (!items.length) return;
    if (start < 0 || start >= items.length) start = 0;
    var id = ++runId;
    var i = start;
    if (opts.onStart) opts.onStart(i);
    step();

    function step() {
      if (id !== runId) return;
      if (i >= items.length) {
        if (opts.onEnd) opts.onEnd();
        return;
      }
      if (opts.onProgress) opts.onProgress(i);
      var u = new SpeechSynthesisUtterance(items[i]);
      u.lang = 'zh-CN';
      u.onend = function () {
        if (id !== runId) return;
        i++;
        step();
      };
      u.onerror = function () {
        if (id !== runId) return;
        if (opts.onEnd) opts.onEnd();
      };
      window.speechSynthesis.speak(u);
    }
  }

  function stop() {
    runId++;
    if (supported) window.speechSynthesis.cancel();
  }

  window.TTS = { speakFrom: speakFrom, stop: stop, supported: supported };
})();
