/* file://에서도 동작하는 새 DC 리포트. 외부 요청이나 모듈을 쓰지 않는다. */
(function () {
    "use strict";

    var ROW_HEIGHT = 36;
    var SPARE_ROWS = 20;

    function showError(message) {
        var box = document.getElementById("dc-error");
        if (box) {
            box.textContent = message;
            box.hidden = false;
        }
    }

    function clearError() {
        var box = document.getElementById("dc-error");
        if (box) {
            box.textContent = "";
            box.hidden = true;
        }
    }

    function guard(fn) {
        return function () {
            try {
                return fn.apply(this, arguments);
            } catch (error) {
                showError("화면을 그리지 못했습니다: " + (error && error.message ? error.message : String(error)));
                return undefined;
            }
        };
    }

    function own(object, key) {
        return Object.prototype.hasOwnProperty.call(object, key);
    }

    function display(value) {
        return value === null || value === undefined || value === "" ? "—" : String(value);
    }

    function columnIndex(cols, name) {
        for (var i = 0; i < cols.length; i += 1) {
            if (cols[i] === name) {
                return i;
            }
        }
        return -1;
    }

    function make(tag, className, text) {
        var node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text !== undefined) {
            node.textContent = text;
        }
        return node;
    }

    function initTable() {
        var viewport = document.getElementById("dc-viewport");
        if (!viewport) {
            return;
        }
        if (!window.__dcTable || !window.__dcTable.cols || !window.__dcTable.rows) {
            showError("표 데이터(data/table.js)를 읽지 못했습니다.");
            return;
        }
        var cols = window.__dcTable.cols;
        var allRows = window.__dcTable.rows;
        var viewRows = allRows.slice();
        var head = document.getElementById("dc-table-head");
        var spacer = document.getElementById("dc-spacer");
        var rowsNode = document.getElementById("dc-rows");
        var count = document.getElementById("table-count");
        var search = document.getElementById("table-search");
        var itemIndex = columnIndex(cols, "ITEM");
        var typeIndex = columnIndex(cols, "data_type");
        var rowIndex = columnIndex(cols, "row");
        var filter = "all";
        var sortColumn = -1;
        var sortDirection = 1;
        var widths = [];
        var gridColumns = [];
        var numeric = [];

        for (var c = 0; c < cols.length; c += 1) {
            var width = cols[c] === "reason" ? 320 : (cols[c] === "ITEM" ? 220 : 148);
            widths.push(width);
            gridColumns.push(width + "px");
            var sawNumber = false;
            var onlyNumbers = true;
            for (var r = 0; r < allRows.length; r += 1) {
                var value = allRows[r][c];
                if (value !== null && value !== undefined && value !== "") {
                    if (typeof value === "number") {
                        sawNumber = true;
                    } else {
                        onlyNumbers = false;
                        break;
                    }
                }
            }
            numeric.push(sawNumber && onlyNumbers);
        }
        var gridTemplate = gridColumns.join(" ");
        var tableWidth = widths.reduce(function (sum, value) { return sum + value; }, 0) + "px";
        head.style.gridTemplateColumns = gridTemplate;
        head.style.width = tableWidth;
        spacer.style.width = tableWidth;

        function compareRows(left, right) {
            var a = left[sortColumn];
            var b = right[sortColumn];
            var aEmpty = a === null || a === undefined || a === "";
            var bEmpty = b === null || b === undefined || b === "";
            if (aEmpty || bEmpty) {
                return aEmpty && bEmpty ? 0 : (aEmpty ? 1 : -1);
            }
            var result;
            if (numeric[sortColumn]) {
                result = a - b;
            } else {
                var aText = String(a);
                var bText = String(b);
                result = aText < bText ? -1 : (aText > bText ? 1 : 0);
            }
            return result * sortDirection;
        }

        function renderHead() {
            head.textContent = "";
            for (var i = 0; i < cols.length; i += 1) {
                var button = make("button", "dc-sort", cols[i]);
                button.type = "button";
                button.setAttribute("data-col", String(i));
                button.title = cols[i] + " 정렬";
                if (i === sortColumn) {
                    button.textContent += sortDirection === 1 ? " ▲" : " ▼";
                    button.setAttribute("aria-sort", sortDirection === 1 ? "ascending" : "descending");
                }
                head.appendChild(button);
            }
        }

        function renderRows() {
            var start = Math.max(0, Math.floor(viewport.scrollTop / ROW_HEIGHT) - SPARE_ROWS);
            var visible = Math.ceil(viewport.clientHeight / ROW_HEIGHT);
            var end = Math.min(viewRows.length, start + visible + SPARE_ROWS * 2);
            rowsNode.textContent = "";
            var fragment = document.createDocumentFragment();
            for (var i = start; i < end; i += 1) {
                var record = viewRows[i];
                var row = make("a", "dc-grid dc-item-row");
                row.href = "analysis.html#item=" + encodeURIComponent(String(record[rowIndex]));
                row.style.top = (i * ROW_HEIGHT) + "px";
                row.style.height = ROW_HEIGHT + "px";
                row.style.gridTemplateColumns = gridTemplate;
                row.style.width = tableWidth;
                row.setAttribute("aria-label", display(record[itemIndex]) + " 분석 열기");
                for (var c = 0; c < cols.length; c += 1) {
                    row.appendChild(make("span", "dc-cell", display(record[c])));
                }
                fragment.appendChild(row);
            }
            rowsNode.appendChild(fragment);
        }

        function applyView(resetScroll) {
            var query = search.value.toLowerCase();
            viewRows = [];
            for (var i = 0; i < allRows.length; i += 1) {
                var record = allRows[i];
                var type = typeIndex >= 0 ? record[typeIndex] : "";
                if (filter === "loq" && type !== "LoQ") {
                    continue;
                }
                if (filter === "not-loq" && type === "LoQ") {
                    continue;
                }
                if (query && String(record[itemIndex] || "").toLowerCase().indexOf(query) < 0) {
                    continue;
                }
                viewRows.push(record);
            }
            if (sortColumn >= 0) {
                viewRows.sort(compareRows);
            }
            spacer.style.height = (viewRows.length * ROW_HEIGHT) + "px";
            count.textContent = viewRows.length + " / " + allRows.length;
            if (resetScroll) {
                viewport.scrollTop = 0;
            }
            renderRows();
        }

        head.addEventListener("click", guard(function (event) {
            var button = event.target.closest("button[data-col]");
            if (!button) {
                return;
            }
            var selected = Number(button.getAttribute("data-col"));
            if (sortColumn === selected) {
                sortDirection *= -1;
            } else {
                sortColumn = selected;
                sortDirection = 1;
            }
            renderHead();
            applyView(false);
        }));
        viewport.addEventListener("scroll", guard(renderRows));
        search.addEventListener("input", guard(function () { applyView(true); }));
        var buttons = document.querySelectorAll("button[data-filter]");
        for (var b = 0; b < buttons.length; b += 1) {
            buttons[b].addEventListener("click", guard(function (event) {
                filter = event.currentTarget.getAttribute("data-filter");
                for (var j = 0; j < buttons.length; j += 1) {
                    buttons[j].setAttribute("aria-pressed", buttons[j] === event.currentTarget ? "true" : "false");
                }
                applyView(true);
            }));
        }
        renderHead();
        applyView(true);
        clearError();
        window.__dcReady = true;
    }

    var chunkLoads = {};
    var requestNumber = 0;

    function chunkName(number) {
        var padded = "00000" + String(number);
        return "data/chunks/c" + padded.slice(-5) + ".js";
    }

    function loadChunk(number, callback) {
        if (own(chunkLoads, number)) {
            var existing = chunkLoads[number];
            if (existing.state === "loading") {
                existing.callbacks.push(callback);
            } else {
                callback(existing.state === "loaded");
            }
            return;
        }
        var entry = {state: "loading", callbacks: [callback], script: null};
        chunkLoads[number] = entry;
        var script = document.createElement("script");
        entry.script = script;
        script.src = chunkName(number);
        script.async = true;
        function finish(loaded) {
            entry.state = loaded ? "loaded" : "error";
            var callbacks = entry.callbacks;
            entry.callbacks = [];
            for (var i = 0; i < callbacks.length; i += 1) {
                callbacks[i](loaded);
            }
        }
        script.onload = guard(function () { finish(true); });
        script.onerror = guard(function () { finish(false); });
        document.head.appendChild(script);
    }

    function initAnalysis() {
        var detail = document.getElementById("item-detail");
        if (!detail) {
            return;
        }
        if (!window.__dcTable || !window.__dcTable.cols || !window.__dcTable.rows) {
            showError("ITEM 표 데이터(data/table.js)를 읽지 못했습니다.");
            return;
        }
        if (!window.__dcIndex) {
            showError("ITEM chunk 목록(data/index.js)을 읽지 못했습니다.");
            return;
        }
        var table = window.__dcTable;
        var itemIndex = columnIndex(table.cols, "ITEM");
        var rowIndex = columnIndex(table.cols, "row");
        var records = {};

        function tableRecord(key) {
            if (own(records, key)) {
                return records[key];
            }
            for (var i = 0; i < table.rows.length; i += 1) {
                if (String(table.rows[i][rowIndex]) === key) {
                    var result = {};
                    for (var c = 0; c < table.cols.length; c += 1) {
                        result[table.cols[c]] = table.rows[i][c];
                    }
                    records[key] = result;
                    return result;
                }
            }
            return null;
        }

        function keyFromHash() {
            var match = /(?:^#|&)item=([^&]*)/.exec(window.location.hash);
            if (match) {
                try {
                    return decodeURIComponent(match[1]);
                } catch (ignore) {
                    return match[1];
                }
            }
            return table.rows.length ? String(table.rows[0][rowIndex]) : "";
        }

        function addCard(list, label, value) {
            var card = make("div", "number-card");
            card.appendChild(make("dt", "", label));
            card.appendChild(make("dd", "", display(value)));
            list.appendChild(card);
        }

        function render(key, item, started) {
            var record = tableRecord(key);
            if (!record) {
                showError("ITEM " + key + "의 표 행이 없습니다.");
                return;
            }
            detail.textContent = "";
            var heading = make("h2", "item-title", display(item.item));
            detail.appendChild(heading);
            if (item.unit) {
                heading.appendChild(make("small", "item-unit", " " + item.unit));
            }
            var facts = make("dl", "fact-grid");
            var factNames = ["verdict_final", "judged_by", "reason"];
            for (var f = 0; f < factNames.length; f += 1) {
                var fact = make("div", "fact");
                fact.appendChild(make("dt", "", factNames[f]));
                fact.appendChild(make("dd", "", display(record[factNames[f]])));
                facts.appendChild(fact);
            }
            detail.appendChild(facts);
            var cards = make("dl", "card-grid numbers");
            var names = ["center", "ci_low", "ci_high", "delta", "LoQ", "LoD", "por_median"];
            for (var n = 0; n < names.length; n += 1) {
                addCard(cards, names[n], record[names[n]]);
            }
            addCard(cards, "n dies", item.die.length);
            for (var p = 0; p < item.cols.length; p += 1) {
                if (/^POR\d+$/.test(item.cols[p])) {
                    addCard(cards, "med_shift_" + item.cols[p], record["med_shift_" + item.cols[p]]);
                    addCard(cards, "sigma_ratio_" + item.cols[p], record["sigma_ratio_" + item.cols[p]]);
                }
            }
            detail.appendChild(cards);
            clearError();
            window.__dcItemMs = Date.now() - started;
            window.__dcReady = true;
        }

        function requestItem() {
            var started = Date.now();
            window.__dcReady = false;
            clearError();
            var key = keyFromHash();
            if (!key) {
                showError("열 ITEM이 없습니다.");
                return;
            }
            if (!own(window.__dcIndex, key)) {
                showError("알 수 없는 ITEM 키 " + key + "입니다. 표에서 행을 다시 선택해 주세요.");
                return;
            }
            if (!tableRecord(key)) {
                showError("ITEM " + key + "의 표 행이 없습니다.");
                return;
            }
            if (window.__dcItem && own(window.__dcItem, key)) {
                render(key, window.__dcItem[key], started);
                return;
            }
            var number = Number(window.__dcIndex[key]);
            if (!isFinite(number) || number < 0 || Math.floor(number) !== number) {
                showError("ITEM " + key + "의 chunk 번호가 올바르지 않습니다.");
                return;
            }
            var thisRequest = ++requestNumber;
            loadChunk(number, guard(function (loaded) {
                if (thisRequest !== requestNumber || keyFromHash() !== key) {
                    return;
                }
                if (!loaded) {
                    showError("ITEM 원데이터 chunk " + chunkName(number) + "를 읽지 못했습니다.");
                    return;
                }
                if (!window.__dcItem || !own(window.__dcItem, key)) {
                    showError("chunk " + chunkName(number) + "에 ITEM " + key + "가 없습니다.");
                    return;
                }
                render(key, window.__dcItem[key], started);
            }));
        }

        document.getElementById("analysis-search").addEventListener("submit", guard(function (event) {
            event.preventDefault();
            var query = document.getElementById("analysis-query").value.toLowerCase();
            if (!query) {
                showError("검색할 ITEM 이름을 입력해 주세요.");
                return;
            }
            for (var i = 0; i < table.rows.length; i += 1) {
                if (String(table.rows[i][itemIndex] || "").toLowerCase().indexOf(query) >= 0) {
                    var key = String(table.rows[i][rowIndex]);
                    if (keyFromHash() === key) {
                        requestItem();
                    } else {
                        window.location.hash = "item=" + encodeURIComponent(key);
                    }
                    return;
                }
            }
            showError("검색어와 일치하는 ITEM이 없습니다.");
        }));
        window.addEventListener("hashchange", guard(requestItem));
        requestItem();
    }

    function init() {
        if (document.getElementById("dc-viewport")) {
            initTable();
        } else if (document.getElementById("item-detail")) {
            initAnalysis();
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", guard(init));
    } else {
        guard(init)();
    }
}());
