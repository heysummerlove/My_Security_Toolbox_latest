(function () {
    const API_BASE_URL = window.location.protocol === "file:"
        ? "http://127.0.0.1:18081/api"
        : `${window.location.origin}/api`;
    const TOKEN_KEY = "mst_auth_token";
    const PAGE_SIZE = 10;

    const state = {
        page: 1,
        total: 0,
        keyword: "",
        severityFilter: "",
        items: [],
        deviceOptions: [],
        issueTypeOptions: [],
        severityOptions: [],
        rectificationStatusOptions: [],
    };

    const els = {
        message: document.getElementById("message"),
        keyword: document.getElementById("keyword"),
        severityFilter: document.getElementById("severity-filter"),
        tableWrap: document.querySelector(".table-wrap"),
        tableBody: document.getElementById("table-body"),
        paginationText: document.getElementById("pagination-text"),
        prevBtn: document.getElementById("prev-btn"),
        nextBtn: document.getElementById("next-btn"),
        addRowBtn: document.getElementById("add-row-btn"),
        exportBtn: document.getElementById("export-btn"),
        searchBtn: document.getElementById("search-btn"),
        refreshBtn: document.getElementById("refresh-btn"),
    };

    function getToken() {
        return sessionStorage.getItem(TOKEN_KEY) || "";
    }

    function setMessage(message, type = "") {
        els.message.textContent = message || "";
        els.message.className = `message ${message ? "show" : ""} ${type}`.trim();
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

    function ensureDeviceNoDatalist() {
        let datalist = document.getElementById("issue-device-no-options");
        if (!datalist) {
            datalist = document.createElement("datalist");
            datalist.id = "issue-device-no-options";
            document.body.appendChild(datalist);
        }
        datalist.innerHTML = state.deviceOptions.map((item) =>
            `<option value="${escapeHtml(item.device_no)}">${escapeHtml(item.device_name || "")}</option>`
        ).join("");
    }

    function selectOptionsHtml(options, selected = "", placeholder = "请选择") {
        return [`<option value="">${placeholder}</option>`]
            .concat(options.map((value) =>
                `<option value="${escapeHtml(value)}"${value === selected ? " selected" : ""}>${escapeHtml(value)}</option>`
            ))
            .join("");
    }

    function newDraftRecord() {
        return {
            id: null,
            issue_no: "自动生成",
            device_no: "",
            test_item: "",
            issue_type: "",
            severity_level: "",
            remediation_suggestion: "",
            rectification_status: "",
        };
    }

    function renderRow(item, index) {
        const rowKey = item.id ? `saved-${item.id}` : `draft-${index}`;
        return `
            <tr data-row-key="${rowKey}" data-record-id="${item.id || ""}">
                <td><input data-field="device_no" type="text" list="issue-device-no-options" value="${escapeHtml(item.device_no || "")}" placeholder="关联附表1设备编号"></td>
                <td><input data-field="issue_no" type="text" value="${escapeHtml(item.issue_no || "自动生成")}" readonly></td>
                <td><input data-field="test_item" type="text" value="${escapeHtml(item.test_item || "")}" placeholder="填写检测项目"></td>
                <td>
                    <select data-field="issue_type">
                        ${selectOptionsHtml(state.issueTypeOptions, item.issue_type || "", "请选择问题类型")}
                    </select>
                </td>
                <td>
                    <select data-field="severity_level">
                        ${selectOptionsHtml(state.severityOptions, item.severity_level || "", "请选择严重等级")}
                    </select>
                </td>
                <td><textarea data-field="remediation_suggestion" placeholder="填写整改建议">${escapeHtml(item.remediation_suggestion || "")}</textarea></td>
                <td>
                    <select data-field="rectification_status">
                        ${selectOptionsHtml(state.rectificationStatusOptions, item.rectification_status || "", "请选择整改状态")}
                    </select>
                </td>
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
            els.tableBody.innerHTML = '<tr><td colspan="8" class="empty">暂无问题记录</td></tr>';
        } else {
            els.tableBody.innerHTML = state.items.map((item, index) => renderRow(item, index)).join("");
        }
        ensureDeviceNoDatalist();
        const totalPages = Math.max(1, Math.ceil(state.total / PAGE_SIZE));
        els.paginationText.textContent = `第 ${state.page} / ${totalPages} 页，共 ${state.total} 条`;
        els.prevBtn.disabled = state.page <= 1;
        els.nextBtn.disabled = state.page >= totalPages;
        bindTableEvents();
    }

    function addDraftRow() {
        state.items.unshift(newDraftRecord());
        renderTable();
        const firstRow = els.tableBody.querySelector('tr[data-row-key^="draft-"]');
        if (els.tableWrap) {
            els.tableWrap.scrollTop = 0;
        }
        firstRow?.querySelector('[data-field="device_no"]')?.focus();
    }

    function getStateItemByRowKey(rowKey) {
        return state.items.find((item, index) => {
            const currentKey = item.id ? `saved-${item.id}` : `draft-${index}`;
            return currentKey === rowKey;
        }) || null;
    }

    function getRowPayload(rowEl) {
        const current = getStateItemByRowKey(rowEl.dataset.rowKey || "") || newDraftRecord();
        const issueNo = rowEl.querySelector('[data-field="issue_no"]')?.value || "";
        return {
            id: Number(rowEl.dataset.recordId || 0) || current.id || null,
            issue_no: issueNo
                ? (issueNo === "自动生成" ? "" : issueNo)
                : (current.issue_no === "自动生成" ? "" : (current.issue_no || "")),
            device_no: rowEl.querySelector('[data-field="device_no"]')?.value.trim() ?? current.device_no ?? "",
            test_item: rowEl.querySelector('[data-field="test_item"]')?.value.trim() ?? current.test_item ?? "",
            issue_type: rowEl.querySelector('[data-field="issue_type"]')?.value ?? current.issue_type ?? "",
            severity_level: rowEl.querySelector('[data-field="severity_level"]')?.value ?? current.severity_level ?? "",
            remediation_suggestion: rowEl.querySelector('[data-field="remediation_suggestion"]')?.value.trim() ?? current.remediation_suggestion ?? "",
            rectification_status: rowEl.querySelector('[data-field="rectification_status"]')?.value ?? current.rectification_status ?? "",
        };
    }

    async function saveSingleRow(rowEl) {
        try {
            const payload = getRowPayload(rowEl);
            const path = payload.id ? `/issue-statistics/${payload.id}` : "/issue-statistics";
            const method = payload.id ? "PUT" : "POST";
            await apiRequest(path, {
                method,
                headers: apiHeaders(true),
                body: JSON.stringify(payload),
            });
            setMessage("保存成功", "success");
            await loadRecords();
        } catch (error) {
            setMessage(error.message || "保存失败", "error");
        }
    }

    async function deleteSingleRow(rowEl) {
        const id = Number(rowEl.dataset.recordId || 0);
        if (!id) {
            rowEl.remove();
            if (!els.tableBody.children.length) {
                renderTable();
            }
            return;
        }
        if (!window.confirm("确认删除这条问题记录吗？")) {
            return;
        }
        try {
            await apiRequest(`/issue-statistics/${id}`, {
                method: "DELETE",
                headers: apiHeaders(false),
            });
            setMessage("删除成功", "success");
            await loadRecords();
        } catch (error) {
            setMessage(error.message || "删除失败", "error");
        }
    }

    async function exportExcel() {
        try {
            await secureDownload("/issue-statistics/export-xlsx", {
                keyword: state.keyword,
                severity_filter: state.severityFilter,
            }, "issue_statistics.xlsx");
        } catch (error) {
            setMessage(error.message || "导出失败", "error");
        }
    }

    function bindTableEvents() {
        els.tableBody.querySelectorAll("[data-save-row]").forEach((btn) => {
            btn.addEventListener("click", () => saveSingleRow(btn.closest("tr")));
        });
        els.tableBody.querySelectorAll("[data-delete-row]").forEach((btn) => {
            btn.addEventListener("click", () => deleteSingleRow(btn.closest("tr")));
        });
    }

    function bindEvents() {
        els.addRowBtn.addEventListener("click", addDraftRow);
        els.exportBtn.addEventListener("click", exportExcel);
        els.searchBtn.addEventListener("click", () => {
            state.keyword = els.keyword.value.trim();
            state.severityFilter = els.severityFilter.value;
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
        els.keyword.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                event.preventDefault();
                state.keyword = els.keyword.value.trim();
                state.severityFilter = els.severityFilter.value;
                state.page = 1;
                loadRecords();
            }
        });
    }

    async function loadOptions() {
        const [optionsResp, devicesResp] = await Promise.all([
            apiRequest("/issue-statistics/options", { method: "GET", headers: apiHeaders(false) }),
            apiRequest("/issue-statistics/devices", { method: "GET", headers: apiHeaders(false) }),
        ]);
        state.issueTypeOptions = optionsResp.data?.issue_type_options || [];
        state.severityOptions = optionsResp.data?.severity_options || [];
        state.rectificationStatusOptions = optionsResp.data?.rectification_status_options || [];
        state.deviceOptions = devicesResp.data || [];
    }

    async function loadRecords() {
        try {
            const response = await apiRequest(
                `/issue-statistics?keyword=${encodeURIComponent(state.keyword)}&severity_filter=${encodeURIComponent(state.severityFilter)}&page=${state.page}&page_size=${PAGE_SIZE}`,
                { method: "GET", headers: apiHeaders(false) }
            );
            const data = response.data || {};
            state.items = data.items || [];
            state.total = Number(data.total || 0);
            renderTable();
        } catch (error) {
            setMessage(error.message || "列表加载失败", "error");
            els.tableBody.innerHTML = '<tr><td colspan="8" class="empty">加载失败</td></tr>';
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
