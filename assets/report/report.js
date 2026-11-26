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

    function fmtNum(value) {
        if (value === null || value === undefined || value === "" ||
                (typeof value === "number" && isNaN(value))) {
            return "—";
        }
        if (typeof value !== "number" || !isFinite(value)) {
            return display(value);
        }
        if (value === 0) {
            return "0";
        }
        var magnitude = Math.abs(value);
        if (magnitude < 1e4 && Math.floor(value) === value) {
            return String(value);
        }
        if (magnitude >= 1e-3 && magnitude < 1e4) {
            return value.toPrecision(3).replace("e+", "e");
        }
        return value.toExponential(2).replace("e+", "e");
    }

    function displayScale(values) {
        var largest = 0;
        for (var i = 0; i < (values || []).length; i += 1) {
            if (finite(values[i])) {
                largest = Math.max(largest, Math.abs(values[i]));
            }
        }
        if (largest === 0) {
            return {factor: 1, k: 0, label: ""};
        }
        var k = Math.floor(Math.log(largest) / Math.LN10);
        if (Math.abs(k) < 3) {
            return {factor: 1, k: 0, label: ""};
        }
        return {factor: Math.pow(10, k), k: k, label: "×1e" + k};
    }

    function columnIndex(cols, name) {
        for (var i = 0; i < cols.length; i += 1) {
            if (cols[i] === name) {
                return i;
            }
        }
        return -1;
    }

    function headTransform(scrollLeft) {
        var shift = finite(scrollLeft) ? scrollLeft : 0;
        return "translateX(" + (-shift) + "px)";
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
        var colDocs = window.__dcTable.meta && window.__dcTable.meta.col_docs ? window.__dcTable.meta.col_docs : {};
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
                var doc = colDocs[cols[i]];
                button.title = doc ? doc.name + " — " + doc.desc + "\n식: " + doc.formula : cols[i] + " 정렬";
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
                    var cellValue = record[c];
                    var numeric = finite(cellValue);
                    var cell = make("span", "dc-cell", numeric ? fmtNum(cellValue) : display(cellValue));
                    if (numeric) {
                        cell.title = String(cellValue);
                    }
                    row.appendChild(cell);
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
        viewport.addEventListener("scroll", guard(function () {
            head.style.transform = headTransform(viewport.scrollLeft);
            renderRows();
        }));
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
        window.__dcReadyMs = performance.now();
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

    var DIE_AXIS = "판정에 쓴 die (wide)";
    var CHART_COLOR = {doe: "#f47230", por: "#7F8A96", inside: "#257de0", ink: "#1D2733", loq: "#00A888"};

    function finite(value) {
        return typeof value === "number" && isFinite(value);
    }

    function meanAll(values) {
        if (!values.length) {
            return null;
        }
        var total = 0;
        for (var i = 0; i < values.length; i += 1) {
            total += values[i];
        }
        return total / values.length;
    }

    function meanFinite(values) {
        var present = [];
        for (var i = 0; i < values.length; i += 1) {
            if (finite(values[i])) {
                present.push(values[i]);
            }
        }
        return meanAll(present);
    }

    function chunkDies(item) {
        var porIndexes = [];
        var porNames = [];
        var doeIndex = columnIndex(item.cols, "DOE");
        for (var c = 0; c < item.cols.length; c += 1) {
            if (/^POR\d+$/.test(item.cols[c])) {
                porIndexes.push(c);
                porNames.push(item.cols[c]);
            }
        }
        var dies = [];
        for (var i = 0; i < item.die.length; i += 1) {
            var values = item.v[i] || [];
            var por = [];
            for (var p = 0; p < porIndexes.length; p += 1) {
                por.push(finite(values[porIndexes[p]]) ? values[porIndexes[p]] : null);
            }
            var label = item.die[i] && item.die[i].length ? item.die[i].join(" / ") : String(i + 1);
            dies.push({name: label, por: por, mean: meanFinite(por),
                       doe: finite(values[doeIndex]) ? values[doeIndex] : null});
        }
        return {dies: dies, porNames: porNames};
    }

    function extent(values, log, extras) {
        var all = (values || []).concat(extras || []);
        var present = [];
        for (var i = 0; i < all.length; i += 1) {
            if (finite(all[i]) && (!log || all[i] > 0)) {
                present.push(all[i]);
            }
        }
        if (!present.length) {
            return log ? {min: 0.1, max: 10} : {min: -1, max: 1};
        }
        var low = Math.min.apply(null, present);
        var high = Math.max.apply(null, present);
        if (log) {
            var logLow = Math.log(low) / Math.LN10;
            var logHigh = Math.log(high) / Math.LN10;
            var logPad = logHigh === logLow ? 0.25 : (logHigh - logLow) * 0.08;
            return {min: Math.pow(10, logLow - logPad), max: Math.pow(10, logHigh + logPad)};
        }
        var span = high === low ? Math.abs(high) || 1 : high - low;
        return {min: low - span * 0.08, max: high + span * 0.08};
    }

    function chartBase() {
        return {
            animation: false,
            legend: {type: "scroll", top: 2, left: 4, right: 4, textStyle: {color: "#55616E", fontSize: 11}},
            tooltip: {trigger: "item", confine: true, axisPointer: {type: "cross"}},
            grid: {left: 78, right: 28, top: 76, bottom: 72, containLabel: false}
        };
    }

    function scaleValue(value, factor) {
        return finite(value) ? value / factor : value;
    }

    function scaleY(points, factor) {
        for (var i = 0; i < points.length; i += 1) {
            points[i].value[1] = scaleValue(points[i].value[1], factor);
        }
    }

    function rawNum(value) {
        return finite(value) ? String(Number(value.toPrecision(15))) : display(value);
    }

    function tooltipValueFormatter(factor) {
        return function (value) {
            if (Array.isArray(value)) {
                var formatted = [];
                for (var i = 0; i < value.length; i += 1) {
                    formatted.push(rawNum(finite(value[i]) ? value[i] * factor : value[i]));
                }
                return formatted.join(", ");
            }
            return rawNum(finite(value) ? value * factor : value);
        };
    }

    function loqPlacement(value, min, max) {
        if (!finite(value)) {
            return null;
        }
        if (value > max) {
            return "above";
        }
        if (value < min) {
            return "below";
        }
        return "in";
    }

    function edgeText(name, rawValues, placement, axis) {
        var arrow = axis === "x" ? (placement === "above" ? "→" : "←")
                                 : (placement === "above" ? "↑" : "↓");
        return name + " " + rawValues.map(fmtNum).join(" / ") + " (범위 밖 " + arrow + ")";
    }

    function edgeLabel(name, rawValue, placement, axis) {
        if (placement !== "above" && placement !== "below") {
            return "";
        }
        return edgeText(name, [rawValue], placement, axis);
    }

    function appendEdgeLabel(option, counts, name, rawValue, placement, axis) {
        if (!edgeLabel(name, rawValue, placement, axis)) {
            return;
        }
        var key = axis + ":" + placement;
        var mergeKey = "name|" + key + "|" + name;
        var merged = counts[mergeKey];
        if (merged) {
            merged.values.push(rawValue);
            merged.graphic.style.text = edgeText(name, merged.values, placement, axis);
            return;
        }
        var index = counts[key] || 0;
        counts[key] = index + 1;
        var values = [rawValue];
        var graphic = {type: "text", silent: true, z: 100,
                       style: {text: edgeText(name, values, placement, axis),
                               fill: CHART_COLOR.loq, fontSize: 11,
                               backgroundColor: "rgba(255,255,255,0.9)",
                               padding: [2, 4]}};
        if (axis === "x") {
            graphic.top = "middle";
            graphic.y = index * 18;
            if (placement === "above") {
                graphic.right = 32;
            } else {
                graphic.left = 82;
            }
        } else {
            graphic.right = 32;
            if (placement === "above") {
                graphic.top = 80 + index * 18;
            } else {
                graphic.bottom = 76 + index * 18;
            }
        }
        counts[mergeKey] = {graphic: graphic, values: values};
        option.graphic = (option.graphic || []).concat([graphic]);
    }

    function scaledAxisName(name, item, scale) {
        if (!scale.label) {
            return name;
        }
        return name + " (" + scale.label + (item.unit ? " " + item.unit : "") + ")";
    }

    function logEmptyPlan(pointCount, loq) {
        var empty = pointCount === 0;
        var helper = empty && finite(loq) && loq > 0;
        return {empty: empty, helper: helper,
                min: helper ? loq / 10 : null, max: helper ? loq * 10 : null};
    }

    function loqLineSeries(loq, min, max) {
        return [
            {name: "LoQ", type: "line", data: [[min, loq], [max, loq]], symbol: "none", silent: true,
             tooltip: {show: false}, lineStyle: {color: CHART_COLOR.loq, type: "dotted", width: 1.5},
             itemStyle: {color: CHART_COLOR.loq}, animation: false},
            {name: "LoQ", type: "line", data: [[loq, min], [loq, max]], symbol: "none", silent: true,
             tooltip: {show: false}, lineStyle: {color: CHART_COLOR.loq, type: "dotted", width: 1.5},
             itemStyle: {color: CHART_COLOR.loq}, animation: false}
        ];
    }

    function marginFor(record, logBases) {
        var basis = String(record.verdict_basis);
        if ((logBases || []).indexOf(basis) >= 0) {
            return {value: record.delta_log, name: "delta_log"};
        }
        if (basis === "abs") {
            return {value: record.abs_delta, name: "abs_delta"};
        }
        if (basis === "accuracy") {
            return {value: finite(record.accuracy_margin) ? Math.max(record.delta, record.accuracy_margin) : record.delta,
                    name: finite(record.accuracy_margin) ? "max(delta, accuracy_margin)" : "delta"};
        }
        if (basis === "limit") {
            return null;
        }
        return {value: record.delta, name: "delta"};
    }

    function scatterLines(low, high, log, delta, loqY, loqX) {
        var lines = [[{name: "y=x", coord: [low, low], lineStyle: {color: "#55616E", type: "solid"}},
                      {coord: [high, high]}]];
        if (finite(delta)) {
            var up = log ? Math.pow(10, delta) : delta;
            var down = log ? Math.pow(10, -delta) : -delta;
            lines.push([{name: log ? "y=x·10^Δlog" : "y=x+Δ", coord: [low, log ? low * up : low + up]},
                        {coord: [high, log ? high * up : high + up]}]);
            lines.push([{name: log ? "y=x·10^-Δlog" : "y=x−Δ", coord: [low, log ? low * down : low + down]},
                        {coord: [high, log ? high * down : high + down]}]);
        }
        if (finite(loqY) && loqY > 0) {
            lines.push({name: "LoQ", yAxis: loqY, lineStyle: {color: CHART_COLOR.loq, type: "dotted"}});
        }
        if (finite(loqX) && loqX > 0) {
            lines.push({name: "LoQ", xAxis: loqX, lineStyle: {color: CHART_COLOR.loq, type: "dotted"}});
        }
        return lines;
    }

    function scatterOption(item, record, log) {
        var parsed = chunkDies(item);
        var series = [{name: "DOE", type: "scatter", symbolSize: 9, data: [],
                       itemStyle: {color: CHART_COLOR.doe, borderColor: "#FFFFFF", borderWidth: 1}}];
        var p;
        for (p = 0; p < parsed.porNames.length; p += 1) {
            series.push({name: parsed.porNames[p], type: "scatter", symbolSize: 8, data: [],
                         itemStyle: {color: CHART_COLOR.por, borderColor: "#FFFFFF", borderWidth: 1}});
        }
        var values = [];
        var dropped = 0;
        for (var i = 0; i < parsed.dies.length; i += 1) {
            var die = parsed.dies[i];
            var invalidLog = false;
            if (log) {
                for (p = 0; p < die.por.length; p += 1) {
                    invalidLog = invalidLog || (finite(die.por[p]) && die.por[p] <= 0);
                }
                invalidLog = invalidLog || (finite(die.doe) && die.doe <= 0);
            }
            if (invalidLog) {
                dropped += 1;
                continue;
            }
            var x = log ? meanFinite(die.por.map(Math.abs)) : die.mean;
            if (!finite(x) || (log && x <= 0)) {
                continue;
            }
            if (finite(die.doe) && (!log || die.doe > 0)) {
                var doeY = log ? Math.abs(die.doe) : die.doe;
                series[0].data.push({name: die.name, value: [x, doeY]});
                values.push(x, doeY);
            }
            for (p = 0; p < die.por.length; p += 1) {
                if (finite(die.por[p]) && (!log || die.por[p] > 0)) {
                    var porY = log ? Math.abs(die.por[p]) : die.por[p];
                    series[p + 1].data.push({name: die.name, value: [x, porY]});
                    values.push(x, porY);
                }
            }
        }
        var scale = log ? {factor: 1, k: 0, label: ""} : displayScale(values.concat([record.delta]));
        if (!log) {
            for (var s = 0; s < series.length; s += 1) {
                for (var d = 0; d < series[s].data.length; d += 1) {
                    series[s].data[d].value[0] = scaleValue(series[s].data[d].value[0], scale.factor);
                    series[s].data[d].value[1] = scaleValue(series[s].data[d].value[1], scale.factor);
                }
            }
            for (var v = 0; v < values.length; v += 1) {
                values[v] = scaleValue(values[v], scale.factor);
            }
        }
        var delta = scaleValue(record[log ? "delta_log" : "delta"], scale.factor);
        var loq = scaleValue(record.LoQ, scale.factor);
        var pointCount = 0;
        for (var sc = 0; sc < series.length; sc += 1) {
            pointCount += series[sc].data.length;
        }
        var emptyPlan = log ? logEmptyPlan(pointCount, loq) : {empty: false, helper: false};
        var extras = [];
        if (finite(delta) && !emptyPlan.empty) {
            var base = extent(values, log);
            if (log) {
                extras = [base.min * Math.pow(10, -delta), base.max * Math.pow(10, delta)];
            } else {
                extras = [base.min - delta, base.max + delta];
            }
        }
        var limits = extent(values, log, extras);
        var markLoqY = null;
        var markLoqX = null;
        var loqYPlacement = null;
        var loqXPlacement = null;
        if (!emptyPlan.helper && finite(loq) && loq > 0) {
            loqYPlacement = loqPlacement(loq, limits.min, limits.max);
            if (loqYPlacement === "in" && !log) {
                markLoqY = loq;
            }
            if (log) {
                loqXPlacement = loqPlacement(loq, limits.min, limits.max);
            }
        }
        if (emptyPlan.helper) {
            limits = {min: emptyPlan.min, max: emptyPlan.max};
            series.push.apply(series, loqLineSeries(loq, limits.min, limits.max));
        }
        // On a log scatter with points, ECharts does not draw LoQ markLines, so an in-range LoQ
        // is a real line pair instead. The empty-log helper above already added its pair (it has
        // no points, so loqYPlacement stays null here) and is never added twice.
        if (log && !emptyPlan.helper && loqYPlacement === "in") {
            series.push.apply(series, loqLineSeries(loq, limits.min, limits.max));
        }
        series[0].markLine = {silent: true, symbol: ["none", "none"], animation: false,
                              lineStyle: {width: 1.5, type: "dashed", color: "#6B7785"},
                              label: {formatter: "{b}", fontSize: 10, color: "#55616E"},
                              data: scatterLines(limits.min, limits.max, log, delta, markLoqY, markLoqX)};
        var option = chartBase();
        option.series = series;
        option.tooltip.valueFormatter = tooltipValueFormatter(scale.factor);
        var edgeCounts = {};
        if (loqYPlacement && loqYPlacement !== "in") {
            appendEdgeLabel(option, edgeCounts, "LoQ", record.LoQ, loqYPlacement, "y");
        }
        if (loqXPlacement && loqXPlacement !== "in") {
            appendEdgeLabel(option, edgeCounts, "LoQ", record.LoQ, loqXPlacement, "x");
        }
        if (emptyPlan.empty) {
            option.graphic = (option.graphic || []).concat([{type: "text", left: "center", top: "middle", silent: true,
                               style: {text: "양수 값 없음: log 축에 점 없음", fill: "#55616E", fontSize: 13}}]);
        }
        option.xAxis = {type: log ? "log" : "value", logBase: 10, min: limits.min, max: limits.max, scale: !log,
                        name: scaledAxisName("POR 회차 평균 · " + DIE_AXIS, item, scale), nameLocation: "middle", nameGap: 44,
                        axisLabel: {color: "#55616E", hideOverlap: true, formatter: fmtNum},
                        splitNumber: log ? 5 : 4,
                        splitLine: {lineStyle: {color: "#E2E6EC"}}};
        option.yAxis = {type: log ? "log" : "value", logBase: 10, min: limits.min, max: limits.max, scale: !log,
                        name: scaledAxisName((log ? "|DOE|·|POR|" : "DOE·POR") + " · " + DIE_AXIS, item, scale),
                        nameLocation: "middle", nameGap: 58, nameRotate: 90,
                        axisLabel: {color: "#55616E", hideOverlap: true, formatter: fmtNum},
                        splitLine: {lineStyle: {color: "#E2E6EC"}}};
        return {option: option, dropped: dropped};
    }

    function quantile(sorted, q) {
        if (!sorted.length) {
            return null;
        }
        var position = (sorted.length - 1) * q;
        var lower = Math.floor(position);
        var fraction = position - lower;
        return sorted[lower] + (sorted[Math.ceil(position)] - sorted[lower]) * fraction;
    }

    function boxOption(item, record) {
        var parsed = chunkDies(item);
        var columns = parsed.porNames.concat(["DOE"]);
        var perColumn = [];
        var porPoints = [];
        var doePoints = [];
        var rawValues = [];
        var c;
        for (c = 0; c < columns.length; c += 1) {
            perColumn.push([]);
        }
        for (var i = 0; i < parsed.dies.length; i += 1) {
            var die = parsed.dies[i];
            for (c = 0; c < columns.length; c += 1) {
                var value = c === columns.length - 1 ? die.doe : die.por[c];
                if (!finite(value)) {
                    continue;
                }
                perColumn[c].push(value);
                rawValues.push(value);
                var jitter = (((i * 37 + c * 17) % 13) - 6) * 0.018;
                var point = {name: die.name, value: [c + jitter, value]};
                (c === columns.length - 1 ? doePoints : porPoints).push(point);
            }
        }
        var boxes = [];
        for (c = 0; c < perColumn.length; c += 1) {
            var sorted = perColumn[c].slice().sort(function (a, b) { return a - b; });
            boxes.push(sorted.length ? [sorted[0], quantile(sorted, 0.25), quantile(sorted, 0.5),
                                        quantile(sorted, 0.75), sorted[sorted.length - 1]] : [null, null, null, null, null]);
        }
        var limits = [];
        for (var l = 0; l < 2; l += 1) {
            var name = l === 0 ? "LoD" : "LoQ";
            if (finite(record[name])) {
                limits.push({name: name, yAxis: record[name], lineStyle: {color: CHART_COLOR.loq, type: "dotted"},
                         label: {formatter: "{b}", position: limits.length % 2 ? "insideEndBottom" : "insideEndTop"}});
            }
        }
        var scale = displayScale(rawValues);
        var values = [];
        for (var v = 0; v < rawValues.length; v += 1) {
            values.push(scaleValue(rawValues[v], scale.factor));
        }
        for (var b = 0; b < boxes.length; b += 1) {
            for (var q = 0; q < boxes[b].length; q += 1) {
                boxes[b][q] = scaleValue(boxes[b][q], scale.factor);
            }
        }
        scaleY(porPoints, scale.factor);
        scaleY(doePoints, scale.factor);
        for (l = 0; l < limits.length; l += 1) {
            limits[l].yAxis = scaleValue(limits[l].yAxis, scale.factor);
        }
        var axisLimits = extent(values, false);
        var option = chartBase();
        option.tooltip.valueFormatter = tooltipValueFormatter(scale.factor);
        var markLimits = [];
        var edgeCounts = {};
        for (l = 0; l < limits.length; l += 1) {
            var placement = loqPlacement(limits[l].yAxis, axisLimits.min, axisLimits.max);
            if (placement === "in") {
                markLimits.push(limits[l]);
            } else {
                appendEdgeLabel(option, edgeCounts, limits[l].name, record[limits[l].name], placement, "y");
            }
        }
        option.series = [
            {name: "분포(box)", type: "boxplot", data: boxes, boxWidth: [8, 24],
             itemStyle: {color: "#EDF3FA", borderColor: "#55616E", borderWidth: 1.5},
             markLine: {silent: true, symbol: ["none", "none"], label: {formatter: "{b}"}, data: markLimits}},
            {name: "POR die", type: "scatter", data: porPoints, symbolSize: 8,
             itemStyle: {color: CHART_COLOR.por, borderColor: "#FFFFFF", borderWidth: 1}},
            {name: "DOE die", type: "scatter", data: doePoints, symbolSize: 8,
             itemStyle: {color: CHART_COLOR.doe, borderColor: "#FFFFFF", borderWidth: 1}}
        ];
        option.xAxis = {type: "category", data: columns, name: "POR/DOE · " + DIE_AXIS,
                        nameLocation: "middle", nameGap: 42, axisLabel: {color: "#55616E"}};
        option.yAxis = {type: "value", scale: true, min: axisLimits.min, max: axisLimits.max,
                        name: scaledAxisName("die 값 · " + DIE_AXIS, item, scale),
                        nameLocation: "middle", nameGap: 58, nameRotate: 90,
                        axisLabel: {color: "#55616E", hideOverlap: true, formatter: fmtNum},
                        splitLine: {lineStyle: {color: "#E2E6EC"}}};
        return option;
    }

    function ciLine(name, value, color, dash) {
        return {name: name, type: "line", data: [[-0.46, value], [0.46, value]], showSymbol: false,
                silent: true, lineStyle: {color: color, width: 1.7, type: dash}, tooltip: {show: false}};
    }

    function ciOption(item, record, logBases) {
        var log = logBases.indexOf(String(record.verdict_basis)) >= 0;
        var suffix = log ? "_log" : "";
        var low = record["ci_low" + suffix];
        var high = record["ci_high" + suffix];
        var center = record["center" + suffix];
        var margin = marginFor(record, logBases);
        var parsed = chunkDies(item);
        var inside = [];
        var outside = [];
        var values = [0];
        for (var i = 0; i < parsed.dies.length; i += 1) {
            var die = parsed.dies[i];
            var d = null;
            if (log) {
                var logs = [];
                for (var p = 0; p < die.por.length; p += 1) {
                    if (finite(die.por[p])) {
                        logs.push(Math.log(Math.abs(die.por[p])) / Math.LN10);
                    }
                }
                var porLog = meanAll(logs);
                if (finite(die.doe) && porLog !== null) {
                    d = Math.log(Math.abs(die.doe)) / Math.LN10 - porLog;
                }
            } else if (finite(die.doe) && die.mean !== null) {
                d = die.doe - die.mean;
            }
            if (!finite(d)) {
                continue;
            }
            var jitter = (((i * 37) % 101) / 100 - 0.5) * 0.36;
            var point = {name: die.name, value: [jitter, d]};
            (finite(low) && finite(high) && low <= d && d <= high ? inside : outside).push(point);
            values.push(d);
        }
        var thresholds = [{name: "center", value: center, color: CHART_COLOR.ink, dash: "solid"},
                          {name: "ci_low", value: low, color: CHART_COLOR.inside, dash: "dashed"},
                          {name: "ci_high", value: high, color: CHART_COLOR.inside, dash: "dashed"}];
        if (margin && finite(margin.value)) {
            thresholds.push({name: "+마진 (" + margin.name + ")", value: margin.value,
                             color: CHART_COLOR.doe, dash: "dashed"},
                            {name: "−마진 (" + margin.name + ")", value: -margin.value,
                             color: CHART_COLOR.doe, dash: "dashed"});
        }
        var loqShifts = [];
        if (finite(record.LoQ) && record.LoQ > 0 && finite(record.por_median)) {
            if (log && Math.abs(record.por_median) > 0) {
                loqShifts.push(Math.log(record.LoQ / Math.abs(record.por_median)) / Math.LN10);
            } else if (!log) {
                loqShifts.push(record.LoQ - record.por_median, -record.LoQ - record.por_median);
            }
        }
        var scaleInput = values.concat([center, low, high]);
        if (margin && finite(margin.value)) {
            scaleInput.push(margin.value, -margin.value);
        }
        var scale = log ? {factor: 1, k: 0, label: ""} : displayScale(scaleInput);
        scaleY(inside, scale.factor);
        scaleY(outside, scale.factor);
        for (var v = 0; v < values.length; v += 1) {
            values[v] = scaleValue(values[v], scale.factor);
        }
        center = scaleValue(center, scale.factor);
        low = scaleValue(low, scale.factor);
        high = scaleValue(high, scale.factor);
        for (var t = 0; t < thresholds.length; t += 1) {
            thresholds[t].value = scaleValue(thresholds[t].value, scale.factor);
        }
        var rawLoqShifts = loqShifts.slice();
        for (var s = 0; s < loqShifts.length; s += 1) {
            loqShifts[s] = scaleValue(loqShifts[s], scale.factor);
        }
        var extras = [center, low, high];
        if (margin && finite(margin.value)) {
            extras.push(scaleValue(margin.value, scale.factor), scaleValue(-margin.value, scale.factor));
        }
        var limits = extent(values, false, extras);
        var option = chartBase();
        option.tooltip.valueFormatter = tooltipValueFormatter(scale.factor);
        option.series = [
            {name: "CI 안 die", type: "scatter", data: inside, symbolSize: 9,
             itemStyle: {color: CHART_COLOR.inside, borderColor: "#FFFFFF", borderWidth: 1}},
            {name: "CI 밖 die", type: "scatter", data: outside, symbolSize: 8,
             itemStyle: {color: CHART_COLOR.por, borderColor: "#FFFFFF", borderWidth: 1}}
        ];
        for (t = 0; t < thresholds.length; t += 1) {
            if (finite(thresholds[t].value)) {
                option.series.push(ciLine(thresholds[t].name, thresholds[t].value,
                                          thresholds[t].color, thresholds[t].dash));
            }
        }
        var edgeCounts = {};
        for (s = 0; s < loqShifts.length; s += 1) {
            if (finite(loqShifts[s])) {
                var placement = loqPlacement(loqShifts[s], limits.min, limits.max);
                if (placement === "in") {
                    option.series.push(ciLine("DOE가 LoQ에 닿는 이동", loqShifts[s], CHART_COLOR.loq, "dotted"));
                } else {
                    appendEdgeLabel(option, edgeCounts, "LoQ 이동", rawLoqShifts[s], placement, "y");
                }
            }
        }
        option.xAxis = {type: "value", min: -0.5, max: 0.5, name: "die (jitter) · " + DIE_AXIS,
                        nameLocation: "middle", nameGap: 40, axisLabel: {show: false}, axisTick: {show: false},
                        splitLine: {show: false}};
        option.yAxis = {type: "value", min: limits.min, max: limits.max,
                        name: scaledAxisName((log ? "d (log10 절댓값 차이)" : "d = DOE − POR 평균") + " · " + DIE_AXIS,
                                             item, scale),
                        nameLocation: "middle", nameGap: 60, nameRotate: 90,
                        axisLabel: {color: "#55616E", hideOverlap: true, formatter: fmtNum},
                        splitLine: {lineStyle: {color: "#E2E6EC"}}};
        return option;
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
        var chartInstances = [];
        var chartIds = ["chart-scatter-lin", "chart-scatter-log", "chart-box", "chart-ci"];

        function disposeCharts() {
            for (var i = 0; i < chartInstances.length; i += 1) {
                chartInstances[i].dispose();
            }
            chartInstances = [];
        }

        function chartShell(id, title, record) {
            var slot = document.getElementById(id);
            slot.textContent = "";
            slot.className = "chart-slot chart-filled";
            slot.appendChild(make("h3", "chart-title", title));
            slot.appendChild(make("p", "chart-verdict", display(record.verdict_final) + " · " +
                                  display(record.judged_by) + " · " + display(record.reason)));
            var plot = make("div", "chart-plot");
            slot.appendChild(plot);
            return plot;
        }

        function renderStaticImage(record, item) {
            var rows = table.meta && table.meta.img_rows ? table.meta.img_rows : [];
            var hasImage = false;
            for (var i = 0; i < rows.length; i += 1) {
                hasImage = hasImage || String(rows[i]) === String(record.row);
            }
            if (!hasImage) {
                detail.appendChild(make("p", "hint static-figure", "정적 그림은 차이 항목만(--images)"));
                return;
            }
            var padded = "00000" + String(record.row);
            var path = "img/i" + padded.slice(-5) + ".png";
            var link = make("a", "static-figure");
            link.href = path;
            var image = make("img", "static-item-image");
            image.src = path;
            image.alt = display(item.item) + " 정적 그림";
            image.loading = "lazy";
            link.appendChild(image);
            detail.appendChild(link);
        }

        function renderCharts(record, item) {
            if (!window.echarts) {
                for (var e = 0; e < chartIds.length; e += 1) {
                    var missing = document.getElementById(chartIds[e]);
                    missing.className = "chart-slot";
                    missing.textContent = "ECharts가 없어 차트를 표시하지 못합니다.";
                }
                showError("ECharts를 읽지 못해 차트는 그리지 않았습니다. ITEM 수치 카드는 그대로 볼 수 있습니다.");
                return;
            }
            var logBases = table.meta && table.meta.log_bases ? table.meta.log_bases : [];
            var definitions = [
                {id: chartIds[0], build: function () {
                    var result = scatterOption(item, record, false);
                    return {title: "Y=X 산점도 (선형)", option: result.option};
                }},
                {id: chartIds[1], build: function () {
                    var result = scatterOption(item, record, true);
                    return {title: "Y=X 산점도 (log 절댓값 · 0/음수 제외 " + result.dropped + "die)", option: result.option};
                }},
                {id: chartIds[2], build: function () {
                    return {title: "POR 회차·DOE 상자그림", option: boxOption(item, record)};
                }},
                {id: chartIds[3], build: function () {
                    var basis = logBases.indexOf(String(record.verdict_basis)) >= 0 ? "log" : "선형";
                    return {title: "die별 이동 d·신뢰구간 (" + basis + ")", option: ciOption(item, record, logBases)};
                }}
            ];
            for (var i = 0; i < definitions.length; i += 1) {
                try {
                    var built = definitions[i].build();
                    var plot = chartShell(definitions[i].id, built.title, record);
                    var chart = window.echarts.init(plot);
                    chartInstances.push(chart);
                    chart.setOption(built.option);
                } catch (error) {
                    var slot = document.getElementById(definitions[i].id);
                    slot.className = "chart-slot";
                    slot.textContent = "이 차트를 그리지 못했습니다.";
                    showError("차트를 그리지 못했습니다: " + (error && error.message ? error.message : String(error)));
                }
            }
        }

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
            card.appendChild(make("dd", "", fmtNum(value)));
            list.appendChild(card);
        }

        function render(key, item, started) {
            disposeCharts();
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
            var measNames = ["calcval", "center_meas", "ci_low_meas", "ci_high_meas", "delta_meas"];
            for (var m = 0; m < measNames.length; m += 1) {
                addCard(cards, measNames[m], record[measNames[m]]);
            }
            if (record.meas_note) {
                addCard(cards, "meas_note", record.meas_note);
            }
            addCard(cards, "n dies", item.die.length);
            for (var p = 0; p < item.cols.length; p += 1) {
                if (/^POR\d+$/.test(item.cols[p])) {
                    addCard(cards, "med_shift_" + item.cols[p], record["med_shift_" + item.cols[p]]);
                    addCard(cards, "sigma_ratio_" + item.cols[p], record["sigma_ratio_" + item.cols[p]]);
                }
            }
            detail.appendChild(cards);
            renderStaticImage(record, item);
            clearError();
            renderCharts(record, item);
            window.__dcItemMs = Date.now() - started;
            window.__dcReady = true;
            window.__dcReadyMs = performance.now();
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
        window.addEventListener("resize", guard(function () {
            for (var i = 0; i < chartInstances.length; i += 1) {
                chartInstances[i].resize();
            }
        }));
        requestItem();
    }

    function init() {
        if (document.getElementById("dc-viewport")) {
            initTable();
        } else if (document.getElementById("item-detail")) {
            initAnalysis();
        }
    }

    if (typeof module === "object" && module.exports) {
        module.exports = {fmtNum: fmtNum, rawNum: rawNum, displayScale: displayScale, extent: extent,
                          marginFor: marginFor, logEmptyPlan: logEmptyPlan, loqLineSeries: loqLineSeries,
                          loqPlacement: loqPlacement, edgeLabel: edgeLabel,
                          appendEdgeLabel: appendEdgeLabel,
                          tooltipValueFormatter: tooltipValueFormatter,
                          ciOption: ciOption, boxOption: boxOption, scatterOption: scatterOption,
                          headTransform: headTransform};
    }
    if (typeof document === "undefined") {
        return;
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", guard(init));
    } else {
        guard(init)();
    }
}());
