(function (root, factory) {
    if (typeof module === "object" && module.exports) module.exports = factory();
    else root.WaterRaceUI = factory();
}(typeof globalThis !== "undefined" ? globalThis : this, function () {
    function parseTimestamp(value) {
        if (!value) return null;
        const text = String(value).trim();
        if (!text) return null;
        const timestamp = Date.parse(text.includes("T") ? text : text.replace(" ", "T"));
        return Number.isFinite(timestamp) ? timestamp : null;
    }

    function isFreshAt(lastUpdate, nowMs, staleMs = 15000) {
        const timestamp = parseTimestamp(lastUpdate);
        if (timestamp === null) return false;
        const age = nowMs - timestamp;
        return age >= 0 && age < staleMs;
    }

    function deriveConnectivity(data, nowMs, staleMs = 15000, apiOk = true) {
        const timestamp = parseTimestamp(data?.last_update);
        const dataAgeMs = timestamp === null ? null : Math.max(0, nowMs - timestamp);
        const deviceFresh = Boolean(data?.online) && timestamp !== null && isFreshAt(data.last_update, nowMs, staleMs);
        const mqtt = data?.mqtt_connected === true ? "connected" : "disconnected";
        let device = "offline";
        if (mqtt === "disconnected" && timestamp !== null) device = "historical";
        else if (deviceFresh) device = "online";
        else if (timestamp !== null) device = "stale";
        return {
            api: apiOk === false ? "error" : "ok",
            mqtt,
            device,
            deviceFresh,
            dataAgeMs,
        };
    }

    function getControlAvailability({ apiOk, mqttConnected, deviceFresh }) {
        if (apiOk !== true) return { enabled: false, reason: "后端接口不可用，暂不能控制设备" };
        if (mqttConnected !== true) return { enabled: false, reason: "MQTT未连接，暂不能控制设备" };
        if (deviceFresh !== true) return { enabled: false, reason: "设备数据已过期，暂不能控制设备" };
        return { enabled: true, reason: "" };
    }

    class AlarmEdgeTracker {
        constructor() { this.previous = null; }
        update(value) {
            const current = Number(value || 0);
            const restored = this.previous !== null && this.previous !== 0 && current === 0;
            this.previous = current;
            return restored;
        }
    }

    function formatAge(ageMs) {
        if (!Number.isFinite(ageMs) || ageMs <= 0) return "刚刚";
        const totalSeconds = Math.round(ageMs / 1000);
        if (totalSeconds < 60) return `约${totalSeconds}秒前`;
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        return `约${minutes}分${String(seconds).padStart(2, "0")}秒前`;
    }

    function createSingleFlightPoller(fetcher, onNewData) {
        let inFlight = null;
        let lastTimestamp = null;
        return function poll() {
            if (inFlight) return inFlight;
            let request;
            try {
                request = fetcher();
            } catch (error) {
                request = Promise.reject(error);
            }
            inFlight = Promise.resolve(request)
                .then(value => {
                    const timestamp = value?.last_update;
                    if (parseTimestamp(timestamp) !== null && timestamp !== lastTimestamp) {
                        lastTimestamp = timestamp;
                        onNewData(value);
                    }
                    return value;
                })
                .finally(() => { inFlight = null; });
            return inFlight;
        };
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    return {
        parseTimestamp,
        isFreshAt,
        deriveConnectivity,
        getControlAvailability,
        AlarmEdgeTracker,
        formatAge,
        createSingleFlightPoller,
        escapeHtml,
    };
}));
