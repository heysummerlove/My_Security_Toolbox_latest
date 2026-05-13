(function () {
    const API_BASE_URL = window.location.protocol === "file:"
        ? "http://127.0.0.1:18081/api"
        : `${window.location.origin}/api`;
    const TOKEN_KEY = "mst_auth_token";
    const PAGE_SIZE = 10;
    const REQUIRES_PROBLEM_RESULTS = new Set(["不合格", "异常"]);
    const RESULT_OPTIONS = ["", "合格", "不合格", "异常", "不涉及"];

    const state = {
        page: 1,
        total: 0,
        keyword: "",
        resultFilter: "",
        items: [],
        selectedIds: new Set(),
        deviceOptions: [],
        deviceMap: new Map(),
        testItems: [],
        testItemMap: new Map(),
    };

    const els = {
        message: document.getElementById("message"),
        keyword: document.getElementById("keyword"),
        resultFilter: document.getElementById("result-filter"),
        tableWrap: document.querySelector(".table-wrap"),
        tableBody: document.getElementById("table-body"),
        paginationText: document.getElementById("pagination-text"),
        prevBtn: document.getElementById("prev-btn"),
        nextBtn: document.getElementById("next-btn"),
        addRowBtn: document.getElementById("add-row-btn"),
        batchSaveBtn: document.getElementById("batch-save-btn"),
        batchSubmitBtn: document.getElementById("batch-submit-btn"),
        batchDeleteBtn: document.getElementById("batch-delete-btn"),
        exportBtn: document.getElementById("export-btn"),
        searchBtn: document.getElementById("search-btn"),
        refreshBtn: document.getElementById("refresh-btn"),
        selectAll: document.getElementById("select-all"),
        selectedCount: document.getElementById("selected-count"),
        testItemCount: document.getElementById("test-item-count"),
    };

    function getToken() {
        return sessionStorage.getItem(TOKEN_KEY) || "";
    }

    function setMessage(message, type = "") {
        els.message.textContent = message || "";
        els.message.className = `message ${message ? "show" : ""} ${type || ""}`.trim();
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function apiHeaders(includeJson = true) {
        const headers = new Headers();
        if (includeJson) {
            headers.set("Content-Type", "application/json");
        }
        const token = getToken();
        if (token) {
            headers.set("Authorization", `Bearer ${token}`);
        }
        return headers;
    }

    async function apiRequest(path, options = {}) {
        const response = await fetch(`${API_BASE_URL}${path}`, {
            ...options,
            headers: options.headers || apiHeaders(true),
        });
        const text = await response.text();
        const payload = text ? JSON.parse(text) : {};
        if (!response.ok || (payload.code && payload.code !== 200)) {
            throw new Error(payload.message || "请求失败");
        }
        return payload;
    }

    async function secureDownload(path, query = {}, fallbackName = "download.bin") {
        const params = new URLSearchParams();
        Object.entries(query).forEach(([key, value]) => {
            if (value !== "" && value !== null && value !== undefined) {
                params.set(key, String(value));
            }
        });
        const response = await fetch(`${API_BASE_URL}${path}${params.toString() ? `?${params.toString()}` : ""}`, {
            method: "GET",
            headers: apiHeaders(false),
        });
        if (!response.ok) {
            let message = "下载失败";
            try {
                const payload = await response.json();
                message = payload.message || message;
            } catch (error) {
            }
            throw new Error(message);
        }
        const blob = await response.blob();
        const disposition = response.headers.get("Content-Disposition") || "";
        const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
        const plainMatch = disposition.match(/filename=\"?([^\";]+)\"?/i);
        const fileName = utf8Match
            ? decodeURIComponent(utf8Match[1])
            : (plainMatch ? plainMatch[1] : fallbackName);
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = fileName;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    }

    function normalizeResult(value) {
        const text = String(value || "").trim();
        const mapping = {
            pass: "合格",
            fail: "不合格",
            failed: "不合格",
            error: "异常",
            exception: "异常",
            na: "不涉及",
            "n/a": "不涉及",
        };
        return mapping[text.toLowerCase()] || text;
    }

    function resultOptionsHtml(selected = "") {
        return RESULT_OPTIONS.map((value) => {
            const label = value || "请选择";
            return `<option value="${value}"${value === selected ? " selected" : ""}>${label}</option>`;
        }).join("");
    }

    function testItemOptionsHtml(selected = "") {
        const list = ['<option value="">请选择测试项目</option>'].concat(
            state.testItems.map((item) =>
                `<option value="${escapeHtml(item.key)}"${item.key === selected ? " selected" : ""}>${escapeHtml(item.label)}</option>`
            )
        );
        return list.join("");
    }

    function ensureDeviceNoDatalist() {
        let datalist = document.getElementById("device-no-options");
        if (!datalist) {
            datalist = document.createElement("datalist");
            datalist.id = "device-no-options";
            document.body.appendChild(datalist);
        }
        datalist.innerHTML = state.deviceOptions.map((item) =>
            `<option value="${escapeHtml(item.device_no)}">${escapeHtml(item.device_name || "")}</option>`
        ).join("");
    }

    function toDateTimeLocal(value) {
        const text = String(value || "").trim();
        if (!text) return "";
        return text.length >= 16 ? text.slice(0, 16).replace(" ", "T") : text.replace(" ", "T");
    }

    function syncSelectionView() {
        els.selectedCount.textContent = String(state.selectedIds.size);
    }

    function newDraftRecord() {
        return {
            id: null,
            device_no: "",
            device_name: "",
            device_type: "",
            device_model: "",
            target_ip: "",
            test_item_key: "",
            test_item_label: "",
            test_method: "",
            test_result: "",
            problem_description: "",
            test_time: "",
            remarks: "",
            record_status: "draft",
        };
    }

    function renderRow(item, index) {
        const result = normalizeResult(item.test_result || "");
        const needsProblem = REQUIRES_PROBLEM_RESULTS.has(result);
        const rowKey = item.id ? `saved-${item.id}` : `draft-${index}`;
        return `
            <tr data-row-key="${rowKey}" data-record-id="${item.id || ""}">
                <td><input type="checkbox" data-select-id="${item.id || ""}" ${item.id && state.selectedIds.has(item.id) ? "checked" : ""}></td>
                <td><input data-field="device_no" type="text" list="device-no-options" value="${escapeHtml(item.device_no || "")}" placeholder="手填或联想附表1"></td>
                <td><input data-field="device_name" type="text" value="${escapeHtml(item.device_name || "")}" placeholder="设备名称"></td>
                <td><input data-field="device_type" type="text" value="${escapeHtml(item.device_type || "")}" placeholder="设备类型"></td>
                <td><input data-field="device_model" type="text" value="${escapeHtml(item.device_model || "")}" placeholder="设备型号"></td>
                <td><input data-field="target_ip" type="text" value="${escapeHtml(item.target_ip || "")}" placeholder="设备IP"></td>
                <td>
                    <select data-field="test_item_key">
                        ${testItemOptionsHtml(item.test_item_key || "")}
                    </select>
                </td>
                <td>
                    <textarea data-field="test_method" placeholder="可自动带入，也可手工调整">${escapeHtml(item.test_method || "")}</textarea>
                    <div class="cell-note">切换测试项目后会自动填充推荐测试方法。</div>
                </td>
                <td>
                    <select data-field="test_result">
                        ${resultOptionsHtml(result)}
                    </select>
                </td>
                <td>
                    <textarea data-field="problem_description" placeholder="${needsProblem ? "请填写问题描述" : "当结果为不合格或异常时需要填写"}" ${needsProblem ? "" : 'style="display:none;"'}>${escapeHtml(item.problem_description || "")}</textarea>
                    <div class="cell-note" data-problem-hint>${needsProblem ? "当前结果需要填写问题描述。" : "当前结果无需填写问题描述。"}</div>
                </td>
                <td><input data-field="test_time" type="datetime-local" value="${toDateTimeLocal(item.test_time)}"></td>
                <td><textarea data-field="remarks" placeholder="备注">${escapeHtml(item.remarks || "")}</textarea></td>
                <td><span class="status-tag ${escapeHtml(item.record_status || "draft")}">${escapeHtml(item.record_status || "draft")}</span></td>
                <td>
                    <div style="display:flex;gap:8px;flex-wrap:wrap;">
                        <button class="mini-btn" type="button" data-save-row>保存</button>
                        <button class="mini-btn" type="button" data-delete-row>删除</button>
                    </div>
                </td>
            </tr>
        `;
    }

    function renderTable() {
        if (!state.items.length) {
            els.tableBody.innerHTML = '<tr><td colspan="14" class="empty">暂无测试记录</td></tr>';
        } else {
            els.tableBody.innerHTML = state.items.map((item, index) => renderRow(item, index)).join("");
        }
        ensureDeviceNoDatalist();
        const totalPages = Math.max(1, Math.ceil(state.total / PAGE_SIZE));
        els.paginationText.textContent = `第 ${state.page} / ${totalPages} 页，共 ${state.total} 条`;
        els.prevBtn.disabled = state.page <= 1;
        els.nextBtn.disabled = state.page >= totalPages;
        bindTableEvents();
        syncSelectionView();
    }

    function addDraftRow() {
        state.items.unshift(newDraftRecord());
        renderTable();
        focusNewDraftRow();
    }

    function focusNewDraftRow() {
        const firstRow = els.tableBody.querySelector('tr[data-row-key^="draft-"]');
        if (!firstRow) return;
        if (els.tableWrap) {
            els.tableWrap.scrollTop = 0;
        }
        const firstInput = firstRow.querySelector('[data-field="device_no"]');
        if (!firstInput) return;
        firstRow.scrollIntoView({ block: "nearest", inline: "nearest" });
        firstInput.focus();
        if (typeof firstInput.select === "function") {
            firstInput.select();
        }
    }

    function getStateItemByRowKey(rowKey) {
        return state.items.find((item, index) => {
            const currentKey = item.id ? `saved-${item.id}` : `draft-${index}`;
            return currentKey === rowKey;
        }) || null;
    }

    function getRowPayload(rowEl) {
        const current = getStateItemByRowKey(rowEl.dataset.rowKey || "") || newDraftRecord();
        const payload = {
            id: Number(rowEl.dataset.recordId || 0) || current.id || null,
            device_no: rowEl.querySelector('[data-field="device_no"]')?.value.trim() ?? current.device_no ?? "",
            device_name: rowEl.querySelector('[data-field="device_name"]')?.value.trim() ?? current.device_name ?? "",
            device_type: rowEl.querySelector('[data-field="device_type"]')?.value.trim() ?? current.device_type ?? "",
            device_model: rowEl.querySelector('[data-field="device_model"]')?.value.trim() ?? current.device_model ?? "",
            target_ip: rowEl.querySelector('[data-field="target_ip"]')?.value.trim() ?? current.target_ip ?? "",
            test_item_key: rowEl.querySelector('[data-field="test_item_key"]')?.value ?? current.test_item_key ?? "",
            test_method: rowEl.querySelector('[data-field="test_method"]')?.value.trim() ?? current.test_method ?? "",
            test_result: rowEl.querySelector('[data-field="test_result"]')?.value ?? current.test_result ?? "",
            problem_description: rowEl.querySelector('[data-field="problem_description"]')?.value.trim() ?? current.problem_description ?? "",
            test_time: rowEl.querySelector('[data-field="test_time"]')?.value ?? current.test_time ?? "",
            remarks: rowEl.querySelector('[data-field="remarks"]')?.value.trim() ?? current.remarks ?? "",
            record_status: rowEl.querySelector(".status-tag")?.textContent ?? current.record_status ?? "draft",
        };
        const itemMeta = state.testItemMap.get(payload.test_item_key);
        if (itemMeta) {
            payload.test_item_label = itemMeta.label;
        } else {
            payload.test_item_label = current.test_item_label || "";
        }
        return payload;
    }

    function applyDeviceLinkage(rowEl) {
        const deviceNo = rowEl.querySelector('[data-field="device_no"]')?.value.trim() || "";
        if (!deviceNo) return;
        const device = state.deviceMap.get(deviceNo);
        if (!device) return;
        const deviceNameEl = rowEl.querySelector('[data-field="device_name"]');
        const deviceTypeEl = rowEl.querySelector('[data-field="device_type"]');
        const deviceModelEl = rowEl.querySelector('[data-field="device_model"]');
        const targetIpEl = rowEl.querySelector('[data-field="target_ip"]');
        if (deviceNameEl) deviceNameEl.value = device.device_name || "";
        if (deviceTypeEl) deviceTypeEl.value = device.device_type || "";
        if (deviceModelEl) deviceModelEl.value = device.device_model || "";
        if (targetIpEl) targetIpEl.value = device.target_ip || "";
    }

    function applyTestItemLinkage(rowEl) {
        const testItemKey = rowEl.querySelector('[data-field="test_item_key"]')?.value || "";
        const itemMeta = state.testItemMap.get(testItemKey);
        const methodEl = rowEl.querySelector('[data-field="test_method"]');
        if (!itemMeta || !methodEl) return;
        if (!methodEl.value.trim()) {
            methodEl.value = itemMeta.method || "";
            return;
        }
        methodEl.value = itemMeta.method || methodEl.value;
    }

    function applyResultLinkage(rowEl) {
        const result = normalizeResult(rowEl.querySelector('[data-field="test_result"]')?.value || "");
        const problemEl = rowEl.querySelector('[data-field="problem_description"]');
        const hintEl = rowEl.querySelector("[data-problem-hint]");
        const needsProblem = REQUIRES_PROBLEM_RESULTS.has(result);
        if (!problemEl || !hintEl) return;
        problemEl.style.display = needsProblem ? "" : "none";
        if (!needsProblem) {
            problemEl.value = "";
        }
        problemEl.placeholder = needsProblem ? "请填写问题描述" : "当结果为不合格或异常时需要填写";
        hintEl.textContent = needsProblem ? "当前结果需要填写问题描述。" : "当前结果无需填写问题描述。";
    }

    async function saveSingleRow(rowEl) {
        try {
            const payload = getRowPayload(rowEl);
            const path = payload.id ? `/basic-test-record/${payload.id}` : "/basic-test-record";
            const method = payload.id ? "PUT" : "POST";
            await apiRequest(path, {
                method,
                headers: apiHeaders(true),
                body: JSON.stringify(payload),
            });
            setMessage("单条保存成功", "success");
            await loadRecords();
        } catch (error) {
            setMessage(error.message || "保存失败", "error");
        }
    }

    async function deleteSingleRow(rowEl) {
        const id = Number(rowEl.dataset.recordId || 0);
        if (!id) {
            const rowKey = rowEl.dataset.rowKey;
            state.items = state.items.filter((item, index) => `draft-${index}` !== rowKey);
            renderTable();
            return;
        }
        if (!window.confirm("确认删除这条测试记录吗？")) return;
        try {
            await apiRequest(`/basic-test-record/${id}`, {
                method: "DELETE",
                headers: apiHeaders(false),
            });
            state.selectedIds.delete(id);
            setMessage("删除成功", "success");
            await loadRecords();
        } catch (error) {
            setMessage(error.message || "删除失败", "error");
        }
    }

    async function batchSave(submit = false) {
        const rows = Array.from(els.tableBody.querySelectorAll("tr[data-row-key]"));
        const payloads = rows.map((rowEl) => getRowPayload(rowEl));
        try {
            await apiRequest("/basic-test-record/batch-save", {
                method: "POST",
                headers: apiHeaders(true),
                body: JSON.stringify({ records: payloads, submit }),
            });
            setMessage(submit ? "批量提交成功" : "批量保存成功", "success");
            await loadRecords();
        } catch (error) {
            setMessage(error.message || "批量操作失败", "error");
        }
    }

    async function batchDelete() {
        if (!state.selectedIds.size) {
            setMessage("请先勾选要删除的记录", "warning");
            return;
        }
        if (!window.confirm(`确认删除已勾选的 ${state.selectedIds.size} 条记录吗？`)) return;
        try {
            await apiRequest("/basic-test-record/batch-delete", {
                method: "POST",
                headers: apiHeaders(true),
                body: JSON.stringify({ ids: Array.from(state.selectedIds) }),
            });
            state.selectedIds.clear();
            setMessage("批量删除成功", "success");
            await loadRecords();
        } catch (error) {
            setMessage(error.message || "批量删除失败", "error");
        }
    }

    async function exportExcel() {
        try {
            await secureDownload("/basic-test-record/export-xlsx", {
                keyword: state.keyword,
                result_filter: state.resultFilter,
            }, "basic_test_record.xlsx");
        } catch (error) {
            setMessage(error.message || "导出失败", "error");
        }
    }

    function bindTableEvents() {
        els.tableBody.querySelectorAll('[data-field="device_no"]').forEach((el) => {
            el.addEventListener("input", () => applyDeviceLinkage(el.closest("tr")));
            el.addEventListener("change", () => applyDeviceLinkage(el.closest("tr")));
        });
        els.tableBody.querySelectorAll('select[data-field="test_item_key"]').forEach((el) => {
            el.addEventListener("change", () => applyTestItemLinkage(el.closest("tr")));
        });
        els.tableBody.querySelectorAll('select[data-field="test_result"]').forEach((el) => {
            el.addEventListener("change", () => applyResultLinkage(el.closest("tr")));
        });
        els.tableBody.querySelectorAll("[data-save-row]").forEach((btn) => {
            btn.addEventListener("click", () => saveSingleRow(btn.closest("tr")));
        });
        els.tableBody.querySelectorAll("[data-delete-row]").forEach((btn) => {
            btn.addEventListener("click", () => deleteSingleRow(btn.closest("tr")));
        });
        els.tableBody.querySelectorAll("[data-select-id]").forEach((checkbox) => {
            checkbox.addEventListener("change", () => {
                const id = Number(checkbox.dataset.selectId || 0);
                if (!id) return;
                if (checkbox.checked) {
                    state.selectedIds.add(id);
                } else {
                    state.selectedIds.delete(id);
                }
                syncSelectionView();
            });
        });
        els.tableBody.querySelectorAll("tr[data-row-key]").forEach((rowEl) => {
            applyTestItemLinkage(rowEl);
            applyResultLinkage(rowEl);
        });
    }

    function bindEvents() {
        els.addRowBtn.addEventListener("click", addDraftRow);
        els.batchSaveBtn.addEventListener("click", () => batchSave(false));
        els.batchSubmitBtn.addEventListener("click", () => batchSave(true));
        els.batchDeleteBtn.addEventListener("click", batchDelete);
        els.exportBtn.addEventListener("click", exportExcel);
        els.searchBtn.addEventListener("click", () => {
            state.keyword = els.keyword.value.trim();
            state.resultFilter = els.resultFilter.value;
            state.page = 1;
            loadRecords();
        });
        els.refreshBtn.addEventListener("click", () => loadRecords());
        els.prevBtn.addEventListener("click", () => {
            if (state.page > 1) {
                state.page -= 1;
                loadRecords();
            }
        });
        els.nextBtn.addEventListener("click", () => {
            const totalPages = Math.max(1, Math.ceil(state.total / PAGE_SIZE));
            if (state.page < totalPages) {
                state.page += 1;
                loadRecords();
            }
        });
        els.selectAll.addEventListener("change", () => {
            if (els.selectAll.checked) {
                state.items.forEach((item) => {
                    if (item.id) state.selectedIds.add(item.id);
                });
            } else {
                state.selectedIds.clear();
            }
            renderTable();
        });
        els.keyword.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                event.preventDefault();
                state.keyword = els.keyword.value.trim();
                state.resultFilter = els.resultFilter.value;
                state.page = 1;
                loadRecords();
            }
        });
    }

    async function loadOptions() {
        const [optionsResp, devicesResp] = await Promise.all([
            apiRequest("/basic-test-record/options", { method: "GET", headers: apiHeaders(false) }),
            apiRequest("/basic-test-record/devices", { method: "GET", headers: apiHeaders(false) }),
        ]);
        state.testItems = optionsResp.data?.test_items || [];
        state.testItemMap = new Map(state.testItems.map((item) => [item.key, item]));
        state.deviceOptions = devicesResp.data || [];
        state.deviceMap = new Map(state.deviceOptions.map((item) => [item.device_no, item]));
        els.testItemCount.textContent = String(state.testItems.length);
    }

    async function loadRecords() {
        try {
            const response = await apiRequest(
                `/basic-test-record?keyword=${encodeURIComponent(state.keyword)}&result_filter=${encodeURIComponent(state.resultFilter)}&page=${state.page}&page_size=${PAGE_SIZE}`,
                { method: "GET", headers: apiHeaders(false) }
            );
            const data = response.data || {};
            state.items = (data.items || []).map((item) => ({
                ...item,
                test_result: normalizeResult(item.test_result),
            }));
            state.total = Number(data.total || 0);
            renderTable();
        } catch (error) {
            setMessage(error.message || "列表加载失败", "error");
            els.tableBody.innerHTML = '<tr><td colspan="14" class="empty">加载失败</td></tr>';
        }
    }

    async function init() {
        try {
            bindEvents();
            await loadOptions();
            await loadRecords();
        } catch (error) {
            setMessage(error.message || "初始化失败", "error");
        }
    }

    init();
})();
