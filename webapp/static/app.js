(function () {
  var state = {
    bookId: null,
    chapters: [],
    interpreting: false,
    currentChapter: -1,
    chapterRatios: {},
    chapterSummaries: {}
  };

  var $ = function (id) { return document.getElementById(id); };
  var fileInput = $('file-input');
  var uploadBtn = $('upload-btn');
  var uploadStatus = $('upload-status');
  var bookCard = $('book-card');
  var bookTitle = $('book-title');
  var bookFilename = $('book-filename');
  var chapterList = $('chapter-list');
  var interpretBtn = $('interpret-btn');
  var emptyState = $('empty-state');
  var report = $('report');
  var overview = $('overview');
  var keyPoints = $('key-points');
  var quotes = $('quotes');
  var qaCard = $('qa-card');
  var questionInput = $('question-input');
  var askBtn = $('ask-btn');
  var answer = $('answer');
  var chapterView = $('chapter-view');
  var chapterViewTitle = $('chapter-view-title');
  var chapterViewContent = $('chapter-view-content');
  var chapterRatio = $('chapter-ratio');
  var summarizeBtn = $('summarize-btn');
  var chapterViewClose = $('chapter-view-close');

  function setStatus(msg, isError) {
    uploadStatus.textContent = msg || '';
    uploadStatus.className = 'status' + (isError ? ' error' : '');
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  async function api(url, options) {
    var resp = await fetch(url, options);
    if (!resp.ok) {
      var err = {};
      try { err = await resp.json(); } catch (e) { /* ignore */ }
      throw new Error(err.detail || '请求失败');
    }
    return resp.json();
  }

  function renderBook(book) {
    state.bookId = book.id;
    state.chapters = book.chapters;
    state.chapterRatios = {};
    state.chapterSummaries = {};
    state.currentChapter = -1;
    bookTitle.textContent = book.title;
    bookFilename.textContent = book.filename;
    chapterList.innerHTML = '';
    book.chapters.forEach(function (ch, i) {
      var li = document.createElement('li');
      li.className = 'chapter-item';
      var idx = document.createElement('span');
      idx.className = 'idx';
      idx.textContent = (i + 1) + '.';
      li.appendChild(idx);
      li.appendChild(document.createTextNode(ch.title));
      li.addEventListener('click', function () { openChapterView(i); });
      chapterList.appendChild(li);
    });
    bookCard.hidden = false;
    emptyState.hidden = true;
    report.hidden = true;
    qaCard.hidden = true;
    chapterView.hidden = true;
    answer.className = 'answer';
    questionInput.value = '';
  }

  function updateChapterTitle(index, title) {
    var items = chapterList.querySelectorAll('li');
    if (items[index]) {
      var textNode = items[index].childNodes[1];
      if (textNode) textNode.nodeValue = title;
    }
  }

  function openChapterView(index) {
    state.currentChapter = index;
    chapterViewTitle.textContent = state.chapters[index].title;
    chapterRatio.value = String(state.chapterRatios[index] || 0.25);
    chapterView.hidden = false;
    condenseChapter();
  }

  function condenseChapter() {
    var index = state.currentChapter;
    if (index < 0) return;
    var ratio = parseFloat(chapterRatio.value);
    state.chapterRatios[index] = ratio;
    var cached = state.chapterSummaries[index];
    if (cached && cached.ratio === ratio) {
      chapterViewContent.innerHTML = '<div class="chapter-summary">' + escapeHtml(cached.summary) + '</div>';
      return;
    }
    chapterViewContent.innerHTML = '<div class="loading">浓缩中...</div>';
    summarizeBtn.disabled = true;
    api('/api/books/' + state.bookId + '/chapters/' + index + '/summarize?ratio=' + ratio, { method: 'POST' })
      .then(function (data) {
        state.chapterSummaries[index] = { ratio: ratio, summary: data.summary };
        chapterViewTitle.textContent = data.title;
        updateChapterTitle(index, data.title);
        chapterViewContent.innerHTML = '<div class="chapter-summary">' + escapeHtml(data.summary) + '</div>';
      })
      .catch(function (err) {
        chapterViewContent.innerHTML = '<div class="error">' + escapeHtml(err.message) + '</div>';
      })
      .finally(function () {
        summarizeBtn.disabled = false;
      });
  }

  chapterRatio.addEventListener('change', condenseChapter);
  summarizeBtn.addEventListener('click', condenseChapter);
  chapterViewClose.addEventListener('click', function () { chapterView.hidden = true; });

  function renderReport(interp) {
    overview.textContent = interp.overview;
    keyPoints.innerHTML = '';
    interp.key_points.forEach(function (p) {
      var li = document.createElement('li');
      li.textContent = p;
      keyPoints.appendChild(li);
    });
    quotes.innerHTML = '';
    interp.quotes.forEach(function (q) {
      var li = document.createElement('li');
      li.textContent = q;
      quotes.appendChild(li);
    });
    report.hidden = false;
    qaCard.hidden = false;
  }

  uploadBtn.addEventListener('click', function () { fileInput.click(); });

  fileInput.addEventListener('change', async function () {
    var file = fileInput.files[0];
    if (!file) return;
    setStatus('上传解析中...');
    var form = new FormData();
    form.append('file', file);
    try {
      var book = await api('/api/books', { method: 'POST', body: form });
      renderBook(book);
      setStatus('解析完成，共 ' + book.chapters.length + ' 个章节');
    } catch (err) {
      setStatus(err.message, true);
    }
    fileInput.value = '';
  });

  interpretBtn.addEventListener('click', async function () {
    if (state.interpreting) return;
    state.interpreting = true;
    interpretBtn.disabled = true;
    interpretBtn.textContent = '生成中...';
    try {
      var interp = await api('/api/books/' + state.bookId + '/interpret', { method: 'POST' });
      renderReport(interp);
      interp.chapters.forEach(function (ch, i) { updateChapterTitle(i, ch.title); });
    } catch (err) {
      setStatus(err.message, true);
    } finally {
      state.interpreting = false;
      interpretBtn.disabled = false;
      interpretBtn.textContent = '生成全书概述';
    }
  });

  askBtn.addEventListener('click', ask);
  questionInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') ask();
  });

  async function ask() {
    var q = questionInput.value.trim();
    if (!q || !state.bookId) return;
    askBtn.disabled = true;
    answer.textContent = '思考中...';
    answer.className = 'answer show';
    try {
      var data = await api('/api/books/' + state.bookId + '/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q })
      });
      answer.textContent = data.answer;
    } catch (err) {
      answer.textContent = err.message;
    } finally {
      askBtn.disabled = false;
    }
  }

  $('export-md').addEventListener('click', function () { download('md'); });
  $('export-html').addEventListener('click', function () { download('html'); });

  function download(fmt) {
    if (!state.bookId) return;
    window.location.href = '/api/books/' + state.bookId + '/report?format=' + fmt;
  }
})();
