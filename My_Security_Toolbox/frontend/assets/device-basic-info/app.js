(function () {
    const API_BASE_URL = window.location.protocol === "file:"
        ? "http://127.0.0.1:18081/api"
        : `${window.location.origin}/api`;
    const TOKEN_KEY = "mst_auth_token";
    const PAGE_SIZE = 10;
    const MAC_PATTERN = /^(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$/;

    const state = {
        currentId: null,
        currentStatus: "draft",
        page: 1,
        total: 0,
        keyword: "",
        items: [],
    };

    const els = {
        form: document.getElementById("device-form"),
        message: document.getElementById("message"),
        currentId: document.getElementById("current-id"),
        currentStatus: document.getElementById("current-status"),
        osChoice: document.getElementById("operating-system-choice"),
        osOtherWrap: document.getElementById("operating-system-other-wrap"),
        osOther: document.getElementById("operating-system-other"),
        keyword: document.getElementById("keyword"),
        tableBody: document.getElementById("table-body"),
        paginationText: document.getElementById("pagination-text"),
        prevBtn: document.getElementById("prev-btn"),
        nextBtn: document.getElementById("next-btn"),
        importFile: document.getElementById("import-file"),
        saveBtn: document.getElementById("save-btn"),
        submitBtn: document.getElementById("submit-btn"),
        resetBtn: document.getElementById("reset-btn"),
        exportBtn: document.getElementById("export-btn"),
        searchBtn: document.getElementById("search-btn"),
        refreshBtn: document.getElementById("refresh-btn"),
    };

    function getToken() {
        return sessionStorage.getItem(TOKEN_KEY) || "";
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function setMessage(message, type = "") {
        els.message.textContent = message || "";
        els.message.className = `message ${message ? "show" : ""} ${type || ""}`.trim();
    }

    function updateStatusView() {
        els.currentId.textContent = state.currentId ? String(state.currentId) : "新建";
        els.currentStatus.textContent = state.currentStatus || "draft";
    }

    function updateOperatingSystemUi() {
        const showOther = els.osChoice.value === "其他";
        els.osOtherWrap.hidden = !showOther;
        if (!showOther) {
            els.osOther.value = "";
        }
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
            const error = new Error(payload.message || "请求失败");
            error.status = response.status;
            throw error;
        }
        return payload;
    }

    async function secureDownload(path, query = {}, fallbackName = "download.bin") {
        const params = new URLSearchParams();
        Object.entries(query).forEach(([key, value]) => {
            if (value !== "" && value !== undefined && value !== null) {
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
            const downloadError = new Error(message);
            downloadError.status = response.status;
            throw downloadError;
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

    function collectPayload(status = state.currentStatus || "draft") {
        const formData = new FormData(els.form);
        const payload = Object.fromEntries(formData.entries());
        payload.record_status = status;
        payload.operating_system = payload.operating_system_choice === "其他"
            ? (payload.operating_system_other || "").trim()
            : (payload.operating_system_choice || "").trim();
        return payload;
    }

    function validateIPv4(value) {
        const parts = value.split(".");
        if (parts.length !== 4) return false;
        return parts.every((part) => {
            if (!/^\d+$/.test(part)) return false;
            const num = Number(part);
            return num >= 0 && num <= 255 && String(num) === String(Number(part));
        });
    }

    function validatePayload(payload) {
        const required = [
            ["device_name", "设备名称"],
            ["device_type", "设备类型"],
            ["department", "设备部门"],
            ["device_no", "设备编号"],
            ["device_level", "设备等级"],
            ["device_model", "型号"],
            ["device_status", "设备状态"],
            ["network_status", "入网状态"],
            ["manufacturer", "设备厂商"],
            ["interface_type", "接口类型"],
            ["protocol", "通信协议"],
            ["software_version", "应用软件及版本"],
            ["device_composition", "硬件配置"],
            ["target_ip", "IP 地址"],
            ["operating_system", "操作系统"],
        ];
        for (const [field, label] of required) {
            if (!(payload[field] || "").trim()) {
                return `${label}不能为空`;
            }
        }
        if (!validateIPv4((payload.target_ip || "").trim())) {
            return "IP 地址格式不正确，请填写合法的 IPv4 地址";
        }
        if ((payload.mac_address || "").trim() && !MAC_PATTERN.test((payload.mac_address || "").trim())) {
            return "MAC 地址格式不正确";
        }
        if (payload.operating_system_choice === "其他" && !(payload.operating_system_other || "").trim()) {
            return "选择“其他”操作系统时必须补充填写";
        }
        return "";
    }

    function fillForm(record) {
        state.currentId = record?.id || null;
        state.currentStatus = record?.record_status || "draft";
        Array.from(els.form.elements).forEach((el) => {
            if (!el.name) return;
            el.value = record?.[el.name] ?? "";
        });
        if (record?.operating_system_choice) {
            els.osChoice.value = record.operating_system_choice;
        } else if (record?.operating_system && !["Windows", "Linux", "Android", "Ubuntu", "CentOS", "Debian", "麒麟", "统信UOS", "VxWorks", "FreeRTOS"].includes(record.operating_system)) {
            els.osChoice.value = "其他";
            els.osOther.value = record.operating_system;
        }
        updateOperatingSystemUi();
        updateStatusView();
    }

    function resetForm() {
        state.currentId = null;
        state.currentStatus = "draft";
        els.form.reset();
        els.osChoice.value = "";
        els.osOther.value = "";
        updateOperatingSystemUi();
        updateStatusView();
    }

    async function saveRecord(status) {
        const payload = collectPayload(status);
        const validationMessage = validatePayload(payload);
        if (validationMessage) {
            setMessage(validationMessage, "error");
            return;
        }
        try {
            const path = state.currentId ? `/device-basic-info/${state.currentId}` : "/device-basic-info";
            const method = state.currentId ? "PUT" : "POST";
            const response = await apiRequest(path, {
                method,
                headers: apiHeaders(true),
                body: JSON.stringify(payload),
            });
            fillForm(response.data || {});
            setMessage(status === "submitted" ? "提交成功" : "保存成功", "success");
            await loadRecords();
        } catch (error) {
            setMessage(error.message || "保存失败", "error");
        }
    }

    async function loadRecords() {
        try {
            const response = await apiRequest(`/device-basic-info?keyword=${encodeURIComponent(state.keyword)}&page=${state.page}&page_size=${PAGE_SIZE}`, {
                method: "GET",
                headers: apiHeaders(false),
            });
            const data = response.data || {};
            state.items = data.items || [];
            state.total = Number(data.total || 0);
            renderTable();
        } catch (error) {
            setMessage(error.message || "列表加载失败", "error");
            els.tableBody.innerHTML = '<tr><td class="empty" colspan="8">加载失败</td></tr>';
        }
    }

    function renderTable() {
        if (!state.items.length) {
            els.tableBody.innerHTML = '<tr><td class="empty" colspan="8">暂无设备记录</td></tr>';
        } else {
            els.tableBody.innerHTML = state.items.map((item) => `
                <tr>
                    <td><span class="status-tag ${escapeHtml(item.record_status || "draft")}">${escapeHtml(item.record_status || "draft")}</span></td>
                    <td>${escapeHtml(item.device_name)}</td>
                    <td>${escapeHtml(item.device_no)}</td>
                    <td>${escapeHtml(item.target_ip)}</td>
                    <td>${escapeHtml(item.operating_system)}</td>
                    <td>${escapeHtml(item.manufacturer)}</td>
                    <td>${escapeHtml(item.update_time || "-")}</td>
                    <td>
                        <div class="table-actions">
                            <button class="mini-btn" type="button" data-edit="${item.id}">带入编辑</button>
                            <button class="mini-btn" type="button" data-copy="${item.id}">联动导入</button>
                            <button class="mini-btn" type="button" data-delete="${item.id}">删除</button>
                        </div>
                    </td>
                </tr>
            `).join("");
        }
        const totalPages = Math.max(1, Math.ceil(state.total / PAGE_SIZE));
        els.paginationText.textContent = `第 ${state.page} / ${totalPages} 页，共 ${state.total} 条`;
        els.prevBtn.disabled = state.page <= 1;
        els.nextBtn.disabled = state.page >= totalPages;
        bindTableActions();
    }

    function bindTableActions() {
        els.tableBody.querySelectorAll("[data-edit]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const id = Number(btn.dataset.edit);
                const record = state.items.find((item) => item.id === id);
                if (record) {
                    fillForm(record);
                    setMessage(`已带入记录：${record.device_name}`, "success");
                    window.scrollTo({ top: 0, behavior: "smooth" });
                }
            });
        });
        els.tableBody.querySelectorAll("[data-copy]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const id = Number(btn.dataset.copy);
                const record = state.items.find((item) => item.id === id);
                if (record) {
                    const cloned = { ...record };
                    delete cloned.id;
                    cloned.device_no = "";
                    cloned.target_ip = "";
                    fillForm(cloned);
                    state.currentId = null;
                    state.currentStatus = "draft";
                    updateStatusView();
                    setMessage("已按当前记录联动导入到表单，请补充新的设备编号和 IP 后保存。", "warning");
                    window.scrollTo({ top: 0, behavior: "smooth" });
                }
            });
        });
        els.tableBody.querySelectorAll("[data-delete]").forEach((btn) => {
            btn.addEventListener("click", async () => {
                const id = Number(btn.dataset.delete);
                const record = state.items.find((item) => item.id === id);
                if (!window.confirm(`确认删除设备记录“${record?.device_name || id}”吗？`)) {
                    return;
                }
                try {
                    await apiRequest(`/device-basic-info/${id}`, {
                        method: "DELETE",
                        headers: apiHeaders(false),
                    });
                    if (state.currentId === id) {
                        resetForm();
                    }
                    setMessage("删除成功", "success");
                    await loadRecords();
                } catch (error) {
                    setMessage(error.message || "删除失败", "error");
                }
            });
        });
    }

    function fileToBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                const result = String(reader.result || "");
                const base64 = result.includes(",") ? result.split(",", 2)[1] : result;
                resolve(base64);
            };
            reader.onerror = () => reject(new Error("文件读取失败"));
            reader.readAsDataURL(file);
        });
    }

    async function importExcel(file) {
        if (!file) return;
        try {
            const base64 = await fileToBase64(file);
            const response = await apiRequest("/device-basic-info/import", {
                method: "POST",
                headers: apiHeaders(true),
                body: JSON.stringify({
                    file_name: file.name,
                    file_content_base64: base64,
                }),
            });
            const data = response.data || {};
            setMessage(`导入成功，处理 ${data.imported_count || 0} 条，跳过 ${data.skipped_count || 0} 条。`, "success");
            state.page = 1;
            await loadRecords();
        } catch (error) {
            setMessage(error.message || "导入失败", "error");
        } finally {
            els.importFile.value = "";
        }
    }

    async function exportExcel() {
        try {
            await secureDownload("/device-basic-info/export-xlsx", {
                keyword: state.keyword,
            }, "device_basic_info.xlsx");
        } catch (error) {
            setMessage(error.message || "导出失败", "error");
        }
    }

    function bindEvents() {
        els.osChoice.addEventListener("change", updateOperatingSystemUi);
        els.saveBtn.addEventListener("click", () => saveRecord("draft"));
        els.submitBtn.addEventListener("click", () => saveRecord("submitted"));
        els.resetBtn.addEventListener("click", () => {
            resetForm();
            setMessage("", "");
        });
        els.exportBtn.addEventListener("click", exportExcel);
        els.searchBtn.addEventListener("click", () => {
            state.keyword = els.keyword.value.trim();
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
        els.importFile.addEventListener("change", () => importExcel(els.importFile.files?.[0]));
        els.keyword.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                event.preventDefault();
                state.keyword = els.keyword.value.trim();
                state.page = 1;
                loadRecords();
            }
        });
    }

    updateOperatingSystemUi();
    updateStatusView();
    bindEvents();
    loadRecords();
})();
