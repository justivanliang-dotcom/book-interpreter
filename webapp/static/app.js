(function () {
  var state = { bookId: null, interpreting: false };

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
  var chapterSummaries = $('chapter-summaries');
  var keyPoints = $('key-points');
  var quotes = $('quotes');
  var qaCard = $('qa-card');
  var questionInput = $('question-input');
  var askBtn = $('ask-btn');
  var answer = $('answer');

  function setStatus(msg, isError) {
    uploadStatus.textContent = msg || '';
    uploadStatus.className = 'status' + (isError ? ' error' : '');
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
    bookTitle.textContent = book.title;
    bookFilename.textContent = book.filename;
    chapterList.innerHTML = '';
    book.chapters.forEach(function (ch, i) {
      var li = document.createElement('li');
      var idx = document.createElement('span');
      idx.className = 'idx';
      idx.textContent = (i + 1) + '.';
      li.appendChild(idx);
      li.appendChild(document.createTextNode(ch.title));
      chapterList.appendChild(li);
    });
    bookCard.hidden = false;
    emptyState.hidden = true;
    report.hidden = true;
    qaCard.hidden = true;
    answer.className = 'answer';
    questionInput.value = '';
  }

  function renderReport(interp) {
    overview.textContent = interp.overview;
    chapterSummaries.innerHTML = '';
    interp.chapters.forEach(function (ch) {
      var div = document.createElement('div');
      div.className = 'chapter-summary';
      var t = document.createElement('div');
      t.className = 'cs-title';
      t.textContent = ch.title;
      var b = document.createElement('div');
      b.className = 'cs-body';
      b.textContent = ch.summary || '（暂无摘要）';
      div.appendChild(t);
      div.appendChild(b);
      chapterSummaries.appendChild(div);
    });
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

  function updateChapterTitles(chapters) {
    var items = chapterList.querySelectorAll('li');
    chapters.forEach(function (ch, i) {
      if (items[i]) {
        var textNode = items[i].childNodes[1];
        if (textNode) textNode.nodeValue = ch.title;
      }
    });
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
    interpretBtn.textContent = '解读中...';
    try {
      var interp = await api('/api/books/' + state.bookId + '/interpret', { method: 'POST' });
      renderReport(interp);
      updateChapterTitles(interp.chapters);
    } catch (err) {
      setStatus(err.message, true);
    } finally {
      state.interpreting = false;
      interpretBtn.disabled = false;
      interpretBtn.textContent = '开始解读';
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
