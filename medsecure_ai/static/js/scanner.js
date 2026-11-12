(function () {
  const root = document.getElementById("scanRoot");
  if (!root) return;
  const mode = root.dataset.mode;
  const $ = (id) => document.getElementById(id);
  const video = $("cam"), ph = $("camPh"), msg = $("scanMsg");
  const startBtn = $("startBtn"), stopBtn = $("stopBtn"), capBtn = $("captureBtn");
  let stream = null, detector = null, running = false, timeout = null;

  function say(text, bad) {
    msg.classList.remove("d-none");
    msg.querySelector("p").textContent = text;
    msg.classList.toggle("ms-status-bad", !!bad);
  }
  function hide() { msg.classList.add("d-none"); }

  async function start() {
    hide();
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      say("Camera is not available in this browser.", true); return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
    } catch (e) {
      say("Camera permission is required to use the live scanner.", true); return;
    }
    video.srcObject = stream; await video.play();
    ph.classList.add("d-none"); root.classList.add("scanning");
    startBtn.disabled = true; stopBtn.disabled = false; if (capBtn) capBtn.disabled = false;
    if (mode !== "live") await startDetect();
  }

  function stop() {
    running = false; clearTimeout(timeout);
    if (stream) stream.getTracks().forEach(t => t.stop());
    stream = null; video.srcObject = null;
    ph.classList.remove("d-none"); root.classList.remove("scanning");
    startBtn.disabled = false; stopBtn.disabled = true; if (capBtn) capBtn.disabled = true;
  }

  async function startDetect() {
    detector = null;
    if ("BarcodeDetector" in window) {
      try {
        const want = mode === "qr" ? ["qr_code"] : ["ean_13", "ean_8", "upc_a", "upc_e", "code_128", "code_39", "itf", "codabar"];
        const have = await BarcodeDetector.getSupportedFormats();
        const f = want.filter(x => have.includes(x));
        if (f.length) detector = new BarcodeDetector({ formats: f });
      } catch (e) {}
    }
    const canJsQr = mode === "qr" && window.jsQR;
    if (!detector && !canJsQr) {
      say("Barcode scanning is not supported in this browser. Please use Chrome or Edge, or upload an image.", true);
      stop(); return;
    }
    say("Scanning... hold the " + (mode === "qr" ? "QR code" : "barcode") + " inside the frame.");
    running = true;
    timeout = setTimeout(() => {
      if (!running) return;
      stop(); say(mode === "qr" ? "QR Code Not Detected." : "Barcode Not Detected.", true);
    }, 25000);
    const canvas = document.createElement("canvas"), ctx = canvas.getContext("2d", { willReadFrequently: true });
    (async function loop() {
      while (running) {
        try {
          let value = null;
          if (detector) {
            const r = await detector.detect(video);
            if (r.length) value = r[0].rawValue;
          } else if (video.videoWidth) {
            canvas.width = video.videoWidth; canvas.height = video.videoHeight;
            ctx.drawImage(video, 0, 0);
            const d = ctx.getImageData(0, 0, canvas.width, canvas.height);
            const c = window.jsQR(d.data, d.width, d.height);
            if (c) value = c.data;
          }
          if (value) { found(value); return; }
        } catch (e) {}
        await new Promise(r => setTimeout(r, 250));
      }
    })();
  }

  function found(value) {
    stop(); hide();
    $("scanValue").textContent = value;
    $("scanResult").classList.remove("d-none");
    fetch(root.dataset.save, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": root.dataset.csrf },
      body: JSON.stringify({ type: mode, value: value }) })
      .then(r => r.json()).then(j => {
        if (j.ok) { $("savedNote").classList.remove("d-none"); $("goAnalyze").classList.remove("d-none"); }
      }).catch(() => {});
  }

  function capture() {
    if (!video.videoWidth) return;
    const c = document.createElement("canvas");
    c.width = video.videoWidth; c.height = video.videoHeight;
    c.getContext("2d").drawImage(video, 0, 0);
    c.toBlob(blob => {
      const dt = new DataTransfer();
      dt.items.add(new File([blob], "capture.jpg", { type: "image/jpeg" }));
      $("liveInput").files = dt.files;
      capBtn.disabled = true; capBtn.textContent = "Analyzing...";
      $("liveForm").submit();
    }, "image/jpeg", 0.92);
  }

  startBtn.addEventListener("click", start);
  stopBtn.addEventListener("click", () => { stop(); hide(); });
  if (capBtn) capBtn.addEventListener("click", capture);
  if ($("againBtn")) $("againBtn").addEventListener("click", () => { $("scanResult").classList.add("d-none"); start(); });
  if ($("copyBtn")) $("copyBtn").addEventListener("click", () => navigator.clipboard && navigator.clipboard.writeText($("scanValue").textContent));
  window.addEventListener("beforeunload", stop);
})();
