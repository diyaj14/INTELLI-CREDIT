
let selectedFiles = [];

// Handle file selection
const fileInput = document.getElementById('pdfInput');
if (fileInput) {
    fileInput.addEventListener('change', (e) => {
        selectedFiles = Array.from(e.target.files);
        updateFileDisplay();
    });
}


function updateFileDisplay() {
    const list = document.getElementById('fileList');
    const targetLabel = document.getElementById('targetName');
    if (!list) return;

    if (selectedFiles.length > 0) {
        // Try to guess company from first filename for UI feedback
        const name = selectedFiles[0].name.split('_')[0].split('.')[0].toUpperCase();
        if (targetLabel) targetLabel.textContent = name + " (EXTRACTING...)";
    }

    list.innerHTML = selectedFiles.map((f, i) => `
        <div style="background: rgba(139, 92, 246, 0.1); border: 1px solid var(--primary-color); padding: 4px 12px; border-radius: 12px; font-size: 0.75rem; color: #fff; display: flex; align-items: center; gap: 8px;">
            <i class="fa-solid fa-file-pdf"></i>
            ${f.name}
            <i class="fa-solid fa-times" onclick="removeFile(${i});" style="cursor:pointer; opacity: 0.6;"></i>
        </div>
    `).join('');
}

window.removeFile = (index) => {
    selectedFiles.splice(index, 1);
    updateFileDisplay();
    if (selectedFiles.length === 0) {
        const targetLabel = document.getElementById('targetName');
        if (targetLabel) targetLabel.textContent = "Apex Textiles Pvt Ltd";
    }
};



async function runFullPipeline(forcedProvider = null) {
    const btn = document.getElementById('startBtn');
    const logsEl = document.getElementById('dataStream');
    const scoreVal = document.getElementById('scoreValue');
    const statusLbl = document.getElementById('statusLbl');
    const circle = document.getElementById('progressCircle');
    const targetLabel = document.getElementById('targetName');

    btn.style.opacity = '0.2';
    btn.disabled = true;
    logsEl.innerHTML = '';
    scoreVal.textContent = '00';
    circle.style.strokeDashoffset = 817;

    try {
        // Step 1: Initialize
        setStep(1);
        statusLbl.textContent = 'M1: SERVER CONNECT';
        await addLogs([{ msg: "Contacting Intelligence Core (Port 8001)...", icon: "fa-server" }]);

        let fd = new FormData();

        // Add files to FormData
        if (selectedFiles.length > 0) {
            selectedFiles.forEach(f => fd.append('files', f));
            await addLogs([{ msg: `Uploading ${selectedFiles.length} document(s)...`, icon: "fa-upload" }]);
        } else {
            fd.append("demo_mode", "true"); // Fallback to Apex Textiles if no file
            fd.append("company_name", "Apex Textiles");
            await addLogs([{ msg: "No files provided. Using Demo Mode (Apex Textiles).", icon: "fa-info-circle" }]);
        }


        if (forcedProvider) {
            fd.append("llm_provider", forcedProvider);
            await addLogs([{ msg: `Forced Mode: Using ${forcedProvider.toUpperCase()} only...`, icon: forcedProvider === 'ollama' ? "fa-cube" : "fa-bolt" }]);
        }


        await addLogs([{ msg: "Performing networking handshake...", icon: "fa-handshake" }]);

        // Start polling for progress
        let progressInterval = null;
        const startPolling = (sid) => {
            progressInterval = setInterval(async () => {
                try {
                    const res = await fetch(`/status/${sid}`);
                    const status = await res.json();
                    if (status.status) {
                        statusLbl.textContent = status.status;
                        const prog = status.progress || 0;
                        scoreVal.textContent = prog.toString().padStart(2, '0');
                        circle.style.strokeDashoffset = 817 * (1 - (prog / 100));
                    }
                } catch (e) {
                    console.warn("Polling error:", e);
                }
            }, 800);
        };


        fetch('/analyze', { method: 'POST', body: fd })
            .then(res => {
                if (!res.ok) throw new Error(`Server responded with ${res.status}`);
                return res.json();
            })
            .then(async data => {
                const sid = data.session_id;
                if (!sid) throw new Error("No session ID returned");

                // Start Polling until "COMPLETED"
                let pollInterval = setInterval(async () => {
                    try {
                        const sRes = await fetch(`/status/${sid}`);
                        const status = await sRes.json();




                        statusLbl.textContent = status.status;

                        // Dynamic Sidebar Highlighting
                        const s1 = document.getElementById('step-1');
                        const s2 = document.getElementById('step-2');
                        const s3 = document.getElementById('step-3');

                        [s1, s2, s3].forEach(s => s.classList.remove('active'));

                        if (status.status.includes("Module 1") || status.status.includes("Scanning")) {
                            s1.classList.add('active');
                        } else if (status.status.includes("Module 2")) {
                            s2.classList.add('active');
                        } else if (status.status.includes("Module 3") || status.status === "COMPLETED") {
                            s3.classList.add('active');
                        }

                        if (status.progress) {

                            scoreVal.textContent = status.progress.toString().padStart(2, '0');
                            circle.style.strokeDashoffset = 817 * (1 - (status.progress / 100));
                        }
                        if (status.status === "ERROR") {

                            statusLbl.style.color = "#ef4444";
                            statusLbl.style.borderColor = "rgba(239, 68, 68, 0.4)";
                            statusLbl.style.background = "rgba(239, 68, 68, 0.1)";
                        } else {
                            statusLbl.style.color = "var(--accent-color)";
                            statusLbl.style.borderColor = "rgba(6, 182, 212, 0.1)";
                            statusLbl.style.background = "rgba(6, 182, 212, 0.05)";
                        }


                        if (status.status === "COMPLETED") {
                            clearInterval(pollInterval);
                            await addLogs([{ msg: "Analysis Complete. Building Memo...", icon: "fa-check-double" }]);

                            // Save the actual result from the status call
                            sessionStorage.setItem('lastAnalysis', JSON.stringify(status.result));
                            setTimeout(() => {
                                window.location.href = 'report.html';
                            }, 1500);
                        } else if (status.status === "ERROR") {
                            clearInterval(pollInterval);
                            throw new Error(status.error);
                        }
                    } catch (e) {
                        console.error("Poll error:", e);
                    }
                }, 1000);
            })
            .catch(async err => {
                console.error(err);


                statusLbl.textContent = 'API ERROR';
                statusLbl.style.color = 'red';
                await addLogs([{ msg: `Connection failed: ${err.message}. Is backend running?`, icon: "fa-triangle-exclamation" }]);
                btn.textContent = 'RETRY';
                btn.style.opacity = '1';
                btn.disabled = false;
            });

    } catch (err) {
        console.error(err);
    }
}



async function addLogs(data) {
    const el = document.getElementById('dataStream');
    for (const log of data) {
        const div = document.createElement('div');
        div.className = 'log-entry';
        div.innerHTML = `<i class="fa-solid ${log.icon}"></i> <span>${log.msg}</span>`;
        el.prepend(div);
        await new Promise(r => setTimeout(r, 600));
    }
}

function updateCircle(pct, val) {
    const c = document.getElementById('progressCircle');
    if (c) {
        c.style.strokeDashoffset = 817 * (1 - pct);
    }
    const scoreVal = document.getElementById('scoreValue');
    if (scoreVal) scoreVal.textContent = val;
}

function setStep(n) {
    document.querySelectorAll('.step-item').forEach((s, i) => {
        s.classList.toggle('active', i + 1 === n);
    });
}

function animateFinal(target) {
    let current = parseInt(document.getElementById('scoreValue').textContent);
    const itv = setInterval(() => {
        if (current >= target) clearInterval(itv);
        else {
            current++;
            document.getElementById('scoreValue').textContent = current;
        }
    }, 20);
}

// Mouse tracking for premium cards
document.querySelectorAll('.panel').forEach(panel => {
    panel.addEventListener('mousemove', e => {
        const rect = panel.getBoundingClientRect();
        panel.style.setProperty('--mouse-x', `${e.clientX - rect.left}px`);
        panel.style.setProperty('--mouse-y', `${e.clientY - rect.top}px`);
    });
});

// Idle breathing animation for the central orb
const svgStage = document.querySelector('.circle-svg');
if (svgStage) {
    let phase = 0;
    setInterval(() => {
        phase += 0.05;
        // Apply a gentle floating rotation and scale to the SVG
        svgStage.style.transform = `rotate(-90deg) scale(${1 + Math.sin(phase) * 0.02})`;
    }, 50);
}
