const window = {}; const document = { querySelectorAll: () => [], getElementById: () => null, addEventListener: () => {} }; const Chart = undefined; 
        let cachedDocs = [];
        let cachedPdfs = [];
        let lastChatLength = 0;
        const maxPoints = 50;
        let timeLabels = [];
        let tempData = [], humData = [], hrData = [], o2Data = [], batData = [];
        let currentZoomSensor = 'temp';

        // Tab Switching Logic (Defined First)
        function switchTab(tabId) {
            console.log("Switching tab to:", tabId);
            const btns = document.querySelectorAll('.tab-btn');
            const panels = document.querySelectorAll('.tab-panel');
            
            btns.forEach(btn => btn.classList.remove('active-tab'));
            panels.forEach(pan => pan.classList.remove('active-panel'));
            
            if (tabId === 'hud') {
                if (btns[0]) btns[0].classList.add('active-tab');
                const pHud = document.getElementById('panel-hud');
                if (pHud) pHud.classList.add('active-panel');
            } else if (tabId === 'docs') {
                if (btns[1]) btns[1].classList.add('active-tab');
                const pDocs = document.getElementById('panel-docs');
                if (pDocs) pDocs.classList.add('active-panel');
                renderPdfViewer();
            } else if (tabId === 'charts') {
                if (btns[2]) btns[2].classList.add('active-tab');
                const pCharts = document.getElementById('panel-charts');
                if (pCharts) pCharts.classList.add('active-panel');
                updateGiantZoomChart();
            }
        }

        // Safe Fallback HTML5 Canvas 2D Line Chart Renderer (Works Offline / No Library Required)
        function drawCanvasLineChart(canvasId, labels, datasets, alertLimit) {
            const canvas = document.getElementById(canvasId);
            if (!canvas) return;
            const ctx = canvas.getContext('2d');
            if (!ctx) return;

            const rect = canvas.getBoundingClientRect();
            canvas.width = canvas.parentElement ? canvas.parentElement.clientWidth : (rect.width || 300);
            canvas.height = canvas.parentElement ? canvas.parentElement.clientHeight : (rect.height || 180);

            const w = canvas.width;
            const h = canvas.height;
            const padL = 35, padR = 15, padT = 20, padB = 25;

            ctx.clearRect(0, 0, w, h);

            if (!datasets || datasets.length === 0 || !datasets[0].data || datasets[0].data.length === 0) {
                ctx.fillStyle = '#94A3B8';
                ctx.font = '12px Rajdhani';
                ctx.fillText('Awaiting telemetry data...', w / 2 - 60, h / 2);
                return;
            }

            // Find min/max across datasets
            let allVals = [];
            datasets.forEach(ds => { if (ds.data) allVals = allVals.concat(ds.data); });
            if (alertLimit) allVals.push(alertLimit);

            let minV = Math.min(...allVals);
            let maxV = Math.max(...allVals);
            if (minV === maxV) { minV -= 5; maxV += 5; }
            const range = (maxV - minV) || 1;

            // Draw grid lines
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
            ctx.lineWidth = 1;
            for (let i = 0; i <= 4; i++) {
                const y = padT + (h - padT - padB) * (i / 4);
                ctx.beginPath();
                ctx.moveTo(padL, y);
                ctx.lineTo(w - padR, y);
                ctx.stroke();

                const val = (maxV - (range * (i / 4))).toFixed(1);
                ctx.fillStyle = '#94A3B8';
                ctx.font = '10px Rajdhani';
                ctx.fillText(val, 5, y + 3);
            }

            // Draw Alert limit line if present
            if (alertLimit) {
                const alertY = padT + (h - padT - padB) * (1 - (alertLimit - minV) / range);
                ctx.strokeStyle = '#FF0055';
                ctx.setLineDash([4, 4]);
                ctx.lineWidth = 1.5;
                ctx.beginPath();
                ctx.moveTo(padL, alertY);
                ctx.lineTo(w - padR, alertY);
                ctx.stroke();
                ctx.setLineDash([]);
            }

            // Draw datasets
            datasets.forEach(ds => {
                const data = ds.data;
                const color = ds.color || '#00F2FE';
                const ptsCount = data.length;

                ctx.strokeStyle = color;
                ctx.lineWidth = 2;
                ctx.beginPath();

                for (let i = 0; i < ptsCount; i++) {
                    const x = padL + (w - padL - padR) * (i / Math.max(ptsCount - 1, 1));
                    const y = padT + (h - padT - padB) * (1 - (data[i] - minV) / range);
                    if (i === 0) ctx.moveTo(x, y);
                    else ctx.lineTo(x, y);
                }
                ctx.stroke();

                // Draw end point glowing dot
                if (ptsCount > 0) {
                    const lastX = padL + (w - padL - padR);
                    const lastY = padT + (h - padT - padB) * (1 - (data[ptsCount - 1] - minV) / range);
                    ctx.fillStyle = color;
                    ctx.beginPath();
                    ctx.arc(lastX, lastY, 4, 0, 2 * Math.PI);
                    ctx.fill();
                }
            });
        }

        // Global Chart instances if Chart.js is present
        let compactTempChart = null, compactHumChart = null, compactHrChart = null, compactBatChart = null, giantZoomChart = null;

        function initCharts() {
            if (typeof Chart === 'undefined') {
                console.warn("Chart.js CDN unavailable — using high-performance HTML5 2D Canvas fallback renderer.");
                return;
            }

            try {
                const compactOptions = {
                    responsive: true, maintainAspectRatio: false, animation: false,
                    scales: { x: { display: false }, y: { ticks: { color: '#94A3B8', font: { size: 9 } } } },
                    plugins: { legend: { display: false } }
                };

                const el1 = document.getElementById('compactTempChart');
                if (el1) compactTempChart = new Chart(el1.getContext('2d'), { type: 'line', data: { labels: timeLabels, datasets: [{ data: tempData, borderColor: '#00F2FE', backgroundColor: 'rgba(0, 242, 254, 0.15)', fill: true, tension: 0.3 }] }, options: compactOptions });

                const el2 = document.getElementById('compactHumChart');
                if (el2) compactHumChart = new Chart(el2.getContext('2d'), { type: 'line', data: { labels: timeLabels, datasets: [{ data: humData, borderColor: '#7928CA', backgroundColor: 'rgba(121, 40, 202, 0.15)', fill: true, tension: 0.3 }] }, options: compactOptions });

                const el3 = document.getElementById('compactHrChart');
                if (el3) compactHrChart = new Chart(el3.getContext('2d'), { type: 'line', data: { labels: timeLabels, datasets: [{ data: hrData, borderColor: '#00FF88', tension: 0.3 }] }, options: compactOptions });

                const el4 = document.getElementById('compactBatChart');
                if (el4) compactBatChart = new Chart(el4.getContext('2d'), { type: 'line', data: { labels: timeLabels, datasets: [{ data: batData, borderColor: '#FFD700', tension: 0.3 }] }, options: compactOptions });

                const el5 = document.getElementById('giantZoomChart');
                if (el5) giantZoomChart = new Chart(el5.getContext('2d'), { type: 'line', data: { labels: timeLabels, datasets: [] }, options: { responsive: true, maintainAspectRatio: false, animation: false, scales: { x: { ticks: { color: '#F1F5F9' } }, y: { ticks: { color: '#F1F5F9' } } }, plugins: { legend: { display: true, labels: { color: '#F1F5F9' } } } } });
            } catch (e) {
                console.error("Error initializing Chart.js:", e);
            }
        }

        function selectZoomChart(sensor) {
            currentZoomSensor = sensor;
            document.querySelectorAll('.zoom-btn').forEach(btn => btn.classList.remove('active-zoom'));
            if (sensor === 'temp' && document.querySelectorAll('.zoom-btn')[0]) document.querySelectorAll('.zoom-btn')[0].classList.add('active-zoom');
            if (sensor === 'hum' && document.querySelectorAll('.zoom-btn')[1]) document.querySelectorAll('.zoom-btn')[1].classList.add('active-zoom');
            if (sensor === 'vitals' && document.querySelectorAll('.zoom-btn')[2]) document.querySelectorAll('.zoom-btn')[2].classList.add('active-zoom');
            if (sensor === 'suit' && document.querySelectorAll('.zoom-btn')[3]) document.querySelectorAll('.zoom-btn')[3].classList.add('active-zoom');
            updateGiantZoomChart();
        }

        function updateGiantZoomChart() {
            const titleEl = document.getElementById('zoom-chart-title');
            if (!titleEl) return;

            if (currentZoomSensor === 'temp') {
                titleEl.innerText = "GRAND FORMAT — Température Scaphandre DHT11 (°C)";
                if (giantZoomChart) {
                    giantZoomChart.data.datasets = [
                        { label: 'Température (°C)', data: tempData, borderColor: '#00F2FE', backgroundColor: 'rgba(0, 242, 254, 0.2)', fill: true, tension: 0.3, pointRadius: 3 },
                        { label: 'Seuil d'Alerte (31.0°C)', data: Array(maxPoints).fill(31.0), borderColor: '#FF0055', borderDash: [6, 6], pointRadius: 0 }
                    ];
                    giantZoomChart.update();
                } else {
                    drawCanvasLineChart('giantZoomChart', timeLabels, [{ name: 'Temp (°C)', data: tempData, color: '#00F2FE' }], 31.0);
                }
            } else if (currentZoomSensor === 'hum') {
                titleEl.innerText = "GRAND FORMAT — Humidité Relative DHT11 (%)";
                if (giantZoomChart) {
                    giantZoomChart.data.datasets = [
                        { label: 'Humidité (%)', data: humData, borderColor: '#7928CA', backgroundColor: 'rgba(121, 40, 202, 0.25)', fill: true, tension: 0.3, pointRadius: 3 },
                        { label: 'Seuil d'Alerte (70.0%)', data: Array(maxPoints).fill(70.0), borderColor: '#FF0055', borderDash: [6, 6], pointRadius: 0 }
                    ];
                    giantZoomChart.update();
                } else {
                    drawCanvasLineChart('giantZoomChart', timeLabels, [{ name: 'Humidité (%)', data: humData, color: '#7928CA' }], 70.0);
                }
            } else if (currentZoomSensor === 'vitals') {
                titleEl.innerText = "GRAND FORMAT — Fréquence Cardiaque (BPM) & Oxygène (%)";
                if (giantZoomChart) {
                    giantZoomChart.data.datasets = [
                        { label: 'Heart Rate (bpm)', data: hrData, borderColor: '#00FF88', tension: 0.3, pointRadius: 3 },
                        { label: 'Oxygen (%)', data: o2Data, borderColor: '#4FACFE', tension: 0.3, pointRadius: 3 }
                    ];
                    giantZoomChart.update();
                } else {
                    drawCanvasLineChart('giantZoomChart', timeLabels, [
                        { name: 'Cardio (BPM)', data: hrData, color: '#00FF88' },
                        { name: 'Oxygen (%)', data: o2Data, color: '#4FACFE' }
                    ]);
                }
            } else if (currentZoomSensor === 'suit') {
                titleEl.innerText = "GRAND FORMAT — Batterie (%) & Pression Scaphandre (hPa)";
                if (giantZoomChart) {
                    giantZoomChart.data.datasets = [
                        { label: 'Battery (%)', data: batData, borderColor: '#FFD700', tension: 0.3, pointRadius: 3 }
                    ];
                    giantZoomChart.update();
                } else {
                    drawCanvasLineChart('giantZoomChart', timeLabels, [{ name: 'Batterie (%)', data: batData, color: '#FFD700' }]);
                }
            }
        }

        async function updateDashboard() {
            try {
                const res = await fetch('/api/data?t=' + Date.now(), { cache: "no-store" });
                const data = await res.json();
                const nowStr = new Date().toLocaleTimeString();

                // Telemetry
                const tel = data.telemetry;
                let curTemp = null, curHum = null, curHr = 78, curO2 = 20.9, curBat = 95;

                if (tel.body_temperature && tel.body_temperature.value !== undefined) {
                    const val = tel.body_temperature.value;
                    const isNum = (typeof val === 'number');
                    const elVal = document.getElementById('temp-val');
                    if (elVal) elVal.innerText = isNum ? val.toFixed(1) : val;
                    if (isNum) curTemp = val;
                    const card = document.getElementById('temp-card');
                    const st = document.getElementById('temp-status');
                    if (card && st) {
                        if (isNum && val > 31.0) {
                            card.style.border = '2px solid #ff0055';
                            card.style.background = 'rgba(255, 0, 85, 0.25)';
                            card.style.boxShadow = '0 0 20px rgba(255, 0, 85, 0.6)';
                            st.innerText = '🚨 ALERTE THERMIQUE: >31°C!';
                            st.style.color = '#ff0055';
                        } else {
                            card.style.border = '1px solid var(--card-border)';
                            card.style.background = 'var(--card-bg)';
                            card.style.boxShadow = 'none';
                            st.innerText = 'LIMIT: 31.0°C | NOMINAL';
                            st.style.color = 'var(--accent-green)';
                        }
                    }
                }

                if (tel.humidity_percent && tel.humidity_percent.value !== undefined) {
                    const val = tel.humidity_percent.value;
                    const isNum = (typeof val === 'number');
                    const elVal = document.getElementById('hum-val');
                    if (elVal) elVal.innerText = isNum ? val.toFixed(1) : val;
                    if (isNum) curHum = val;
                    const card = document.getElementById('hum-card');
                    const st = document.getElementById('hum-status');
                    if (card && st) {
                        if (isNum && val > 70.0) {
                            card.style.border = '2px solid #ff0055';
                            card.style.background = 'rgba(255, 0, 85, 0.25)';
                            card.style.boxShadow = '0 0 20px rgba(255, 0, 85, 0.6)';
                            st.innerText = '🚨 ALERTE HUMIDITÉ: >70%!';
                            st.style.color = '#ff0055';
                        } else {
                            card.style.border = '1px solid var(--card-border)';
                            card.style.background = 'var(--card-bg)';
                            card.style.boxShadow = 'none';
                            st.innerText = 'LIMIT: 70.0% | NOMINAL';
                            st.style.color = 'var(--accent-green)';
                        }
                    }
                }

                if (tel.o2_percent && tel.o2_percent.value !== undefined) {
                    curO2 = Number(tel.o2_percent.value);
                    const elO2 = document.getElementById('o2-val');
                    if (elO2) elO2.innerText = curO2.toFixed(1);
                }
                if (tel.co2_ppm && tel.co2_ppm.value !== undefined) {
                    const elCo2 = document.getElementById('co2-val');
                    if (elCo2) elCo2.innerText = Number(tel.co2_ppm.value).toFixed(0);
                }
                if (tel.heart_rate && tel.heart_rate.value !== undefined) {
                    curHr = Number(tel.heart_rate.value);
                    const elHr = document.getElementById('hr-val');
                    if (elHr) elHr.innerText = curHr.toFixed(0);
                }
                if (tel.suit_pressure_hpa && tel.suit_pressure_hpa.value !== undefined) {
                    const elPres = document.getElementById('pres-val');
                    if (elPres) elPres.innerText = Number(tel.suit_pressure_hpa.value).toFixed(0);
                }
                if (tel.battery_percent && tel.battery_percent.value !== undefined) {
                    curBat = Number(tel.battery_percent.value);
                    const elBat = document.getElementById('bat-val');
                    if (elBat) elBat.innerText = curBat.toFixed(0);
                }

                // Update Charts Data
                timeLabels.push(nowStr);
                tempData.push(curTemp !== null ? curTemp : (24.0 + Math.random() * 0.5));
                humData.push(curHum !== null ? curHum : (50.0 + Math.random() * 1.0));
                hrData.push(curHr);
                o2Data.push(curO2);
                batData.push(curBat);

                if (timeLabels.length > maxPoints) {
                    timeLabels.shift();
                    tempData.shift();
                    humData.shift();
                    hrData.shift();
                    o2Data.shift();
                    batData.shift();
                }

                // Update Chart.js or Canvas Fallback
                if (compactTempChart) {
                    compactTempChart.update();
                    compactHumChart.update();
                    compactHrChart.update();
                    compactBatChart.update();
                } else {
                    drawCanvasLineChart('compactTempChart', timeLabels, [{ name: 'Temp (°C)', data: tempData, color: '#00F2FE' }]);
                    drawCanvasLineChart('compactHumChart', timeLabels, [{ name: 'Humidity (%)', data: humData, color: '#7928CA' }]);
                    drawCanvasLineChart('compactHrChart', timeLabels, [{ name: 'Heart Rate (bpm)', data: hrData, color: '#00FF88' }]);
                    drawCanvasLineChart('compactBatChart', timeLabels, [{ name: 'Battery (%)', data: batData, color: '#FFD700' }]);
                }

                updateGiantZoomChart();

                // Procedure
                const proc = data.procedure;
                if (proc) {
                    const stepStr = (proc.step && proc.step > 0) ? ' — Step ' + proc.step : '';
                    const elTitle = document.getElementById('proc-title');
                    const elDesc = document.getElementById('proc-desc');
                    if (elTitle) elTitle.innerText = (proc.title || 'AOUDA Standby') + stepStr;
                    if (elDesc) elDesc.innerText = proc.instruction || 'Say "AOUDA" to initiate voice session.';
                }

                // Chat Feed
                if (data.chat && data.chat.length > 0) {
                    const chatContainer = document.getElementById('chat-feed');
                    if (chatContainer) {
                        chatContainer.innerHTML = '';
                        data.chat.forEach(msg => {
                            const box = document.createElement('div');
                            box.className = 'chat-bubble';
                            const spClass = (msg.speaker === 'Astronaut') ? 'chat-speaker-astro' : 'chat-speaker-aouda';
                            box.innerHTML = `<span class="${spClass}">${msg.speaker}:</span> <span>"${msg.text}"</span><span class="chat-time">${msg.time}</span>`;
                            chatContainer.appendChild(box);
                        });
                        if (data.chat.length !== lastChatLength) {
                            lastChatLength = data.chat.length;
                            chatContainer.scrollTop = chatContainer.scrollHeight;
                        }
                    }
                }

                // Documents & PDFs dropdown populate once
                if (data.documents && cachedDocs.length === 0) {
                    cachedDocs = data.documents;
                    populateDocDropdown();
                }
                if (data.pdf_documents && cachedPdfs.length === 0) {
                    cachedPdfs = data.pdf_documents;
                    populatePdfDropdown();
                }

                // Events
                if (data.events && data.events.length > 0) {
                    const logContainer = document.getElementById('log-feed');
                    if (logContainer) {
                        logContainer.innerHTML = '';
                        data.events.forEach(ev => {
                            const item = document.createElement('div');
                            item.style.fontSize = '12px'; item.style.color = 'var(--text-dim)';
                            item.innerHTML = `<span style="color:var(--cyan-glow); margin-right:8px; font-weight:700;">${ev.time}</span>${ev.event}`;
                            logContainer.appendChild(item);
                        });
                    }
                }
            } catch (e) {
                console.error("Error fetching live dashboard data:", e);
            }
        }

        function populateDocDropdown() {
            const select1 = document.getElementById('doc-dropdown');
            if (!select1) return;
            select1.innerHTML = '<option value="">-- Choose Mission Document --</option>';

            cachedDocs.forEach(doc => {
                const opt1 = document.createElement('option');
                opt1.value = doc.id;
                opt1.innerText = doc.title + ' (' + doc.filename + ')';
                select1.appendChild(opt1);
            });

            if (cachedDocs.length > 0) {
                select1.selectedIndex = 1;
                renderSelectedDoc();
            }
        }

        function populatePdfDropdown() {
            const select2 = document.getElementById('pdf-doc-dropdown');
            if (!select2) return;
            select2.innerHTML = '<option value="">-- Select Official PDF Manual --</option>';

            cachedPdfs.forEach(pdf => {
                const opt = document.createElement('option');
                opt.value = pdf.url;
                opt.innerText = pdf.title + ' (' + pdf.filename + ')';
                select2.appendChild(opt);
            });

            if (cachedPdfs.length > 0) {
                select2.selectedIndex = 0;
                renderPdfViewer();
            }
        }

        function renderSelectedDoc() {
            const select = document.getElementById('doc-dropdown');
            if (!select) return;
            const docId = select.value;
            const container = document.getElementById('doc-steps-container');
            if (!container) return;
            container.innerHTML = '';

            const doc = cachedDocs.find(d => d.id === docId);
            if (!doc) {
                container.innerHTML = '<div style="font-size:13px; color:var(--text-dim); padding:10px;">Select a document.</div>';
                return;
            }

            if (!doc.steps || doc.steps.length === 0) {
                container.innerHTML = `<div style="font-size:13px; color:var(--text-dim); padding:10px;">No steps found. Plain document.</div>`;
                return;
            }

            doc.steps.forEach(stepText => {
                const item = document.createElement('div');
                item.className = 'step-item';
                item.innerHTML = `<span>${stepText}</span> <button class="step-btn-push" onclick="triggerStepQuery('${doc.title}', '${stepText}')">ACTIVATE</button>`;
                container.appendChild(item);
            });
        }

        function renderPdfViewer() {
            const select = document.getElementById('pdf-doc-dropdown');
            const iframe = document.getElementById('pdf-viewer-frame');
            if (!iframe) return;
            const pdfUrl = select ? select.value : '';
            if (pdfUrl) {
                iframe.src = pdfUrl;
            } else if (cachedPdfs.length > 0) {
                iframe.src = cachedPdfs[0].url;
            }
        }

        function filterSteps() {
            const input = document.getElementById('search-input');
            if (!input) return;
            const query = input.value.toLowerCase();
            const items = document.querySelectorAll('.step-item');
            items.forEach(item => {
                if (item.innerText.toLowerCase().includes(query)) {
                    item.style.display = 'flex';
                } else {
                    item.style.display = 'none';
                }
            });
        }

        function triggerStepQuery(docTitle, stepText) {
            const cmd = `query:${stepText}`;
            sendTrigger(cmd);
        }

        function sendCustomQuery() {
            const input = document.getElementById('custom-query');
            if (!input) return;
            const query = input.value.trim();
            if (!query) return;
            sendTrigger('query:' + query);
            input.value = '';
        }

        async function sendTrigger(cmd) {
            try {
                await fetch('/api/trigger?cmd=' + encodeURIComponent(cmd), { cache: "no-store" });
                updateDashboard();
            } catch (e) {
                console.error("Error sending trigger:", e);
            }
        }

        // Initialize Everything Safely
        window.addEventListener('DOMContentLoaded', () => {
            initCharts();
            updateDashboard();
            setInterval(updateDashboard, 500);
        });
        
        // Immediate fallback start
        initCharts();
        updateDashboard();
        setInterval(updateDashboard, 500);
    