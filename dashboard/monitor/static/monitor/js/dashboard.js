(() => {
  const refreshStatus = document.getElementById("auto-refresh-status");
  const stats = document.querySelectorAll("[data-stat]");
  const lastScan = document.getElementById("last-scan");
  const chartCanvas = document.getElementById("scan-history-chart");
  let scanChart;

  async function fetchJson(url) {
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    if (!response.ok) {
      throw new Error(`Yêu cầu ${url} thất bại (HTTP ${response.status})`);
    }
    return response.json();
  }

  async function refreshDashboard() {
    try {
      const requests = [fetchJson("/api/stats/")];
      if (chartCanvas) {
        requests.push(fetchJson("/api/scan-history/?limit=30"));
      }

      const [summary, history] = await Promise.all(requests);
      for (const element of stats) {
        const key = element.dataset.stat;
        const values = {
          total: summary.total_clients,
          connected: summary.connected_clients,
          stale: summary.stale_clients,
          disconnected: summary.disconnected_clients,
        };
        if (Object.prototype.hasOwnProperty.call(values, key)) {
          element.textContent = values[key];
        }
      }
      if (lastScan && summary.last_scan) {
        lastScan.textContent = summary.last_scan;
      }

      if (chartCanvas && window.Chart) {
        const labels = history.scan_history.map((scan) => scan.timestamp);
        const total = history.scan_history.map((scan) => scan.total_clients);
        const connected = history.scan_history.map((scan) => scan.connected_clients);
        if (!scanChart) {
          scanChart = new Chart(chartCanvas, {
            type: "line",
            data: {
              labels,
              datasets: [
                { label: "Tổng client", data: total, borderColor: "#0d6efd", tension: 0.25 },
                { label: "Đang kết nối", data: connected, borderColor: "#198754", tension: 0.25 },
              ],
            },
            options: {
              maintainAspectRatio: false,
              interaction: { intersect: false, mode: "index" },
              scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
            },
          });
        } else {
          scanChart.data.labels = labels;
          scanChart.data.datasets[0].data = total;
          scanChart.data.datasets[1].data = connected;
          scanChart.update();
        }
      }

      if (refreshStatus) {
        refreshStatus.textContent = "Tự động cập nhật";
        refreshStatus.classList.remove("text-warning");
      }
    } catch (error) {
      console.error("Không thể làm mới dữ liệu dashboard:", error);
      if (refreshStatus) {
        refreshStatus.textContent = "Không thể cập nhật dữ liệu";
        refreshStatus.classList.add("text-warning");
      }
    }
  }

  refreshDashboard();
  window.setInterval(refreshDashboard, 15000);
})();
