(function () {
  const el = document.getElementById("msBubbleText");
  if (!el) return;
  const svg = document.getElementById("msMascot");
  const btn = document.getElementById("msVoiceBtn");
  const name = el.dataset.name || "";
  const h = new Date().getHours();
  const greet = h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";

  let msgs = [];
  try { msgs = JSON.parse(el.dataset.msgs || "[]"); } catch (e) {}
  if (!msgs.length) msgs = [
    "Hi" + (name ? " " + name : "") + "! 👋",
    greet + "! Welcome to MedSecure AI",
    "Be safe. Scan before you take!",
    "Always check the expiry date.",
    "Buy medicines from licensed pharmacies."
  ];

  const KEY = "msVoice";
  let voiceOn = false;
  try { voiceOn = localStorage.getItem(KEY) === "1"; } catch (e) {}
  let activated = false, cur = msgs[0], i = 0, timer = null;
  const canSpeak = "speechSynthesis" in window;
  if (!canSpeak && btn) btn.style.display = "none";

  function icon() {
    if (btn) btn.innerHTML = voiceOn ? '<i class="bi bi-volume-up-fill"></i>' : '<i class="bi bi-volume-mute"></i>';
  }
  function speak(text) {
    if (!voiceOn || !canSpeak || !activated) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text.replace(/[^\w\s.,!?']/g, ""));
    u.rate = 0.95; u.pitch = 1.1;
    u.onstart = () => svg.classList.add("talking");
    u.onend = u.onerror = () => svg.classList.remove("talking");
    window.speechSynthesis.speak(u);
  }
  function type(text, done) {
    let n = 0; el.textContent = "";
    svg.classList.add("talking"); clearInterval(timer);
    timer = setInterval(() => {
      el.textContent = text.slice(0, ++n);
      if (n >= text.length) { clearInterval(timer); if (!voiceOn) svg.classList.remove("talking"); done && done(); }
    }, 35);
  }
  function next() {
    cur = msgs[i % msgs.length]; i++;
    type(cur, () => setTimeout(next, 3200));
    speak(cur);
  }

  // Browsers allow voice only after a click/tap. First touch on the page unlocks it.
  function unlock() { activated = true; if (voiceOn) speak(cur); }
  ["pointerdown", "keydown"].forEach(ev => document.addEventListener(ev, unlock, { once: true }));

  if (btn) btn.addEventListener("click", (e) => {
    e.stopPropagation();
    activated = true; voiceOn = !voiceOn;
    try { localStorage.setItem(KEY, voiceOn ? "1" : "0"); } catch (x) {}
    icon();
    if (voiceOn) speak(cur); else if (canSpeak) { window.speechSynthesis.cancel(); svg.classList.remove("talking"); }
  });
  icon(); next();
})();
